from dataclasses import dataclass
from enum import Enum
from logging import getLogger
from typing import Optional
from typing_extensions import Never
from dataclasses_json import DataClassJsonMixin
import stripe
from stripe.error import InvalidRequestError, StripeError, CardError

from stripe import PaymentIntent
from membership.models import Member
from shop.stripe_customer import get_and_sync_stripe_customer
from service.db import db_session
from service.error import InternalServerError, EXCEPTION, BadRequest
from shop.models import Transaction, StripePending
from shop.stripe_constants import (
    MakerspaceMetadataKeys,
    PaymentIntentStatus,
    PaymentIntentNextActionType,
    CURRENCY,
    SetupFutureUsage,
)
from shop.stripe_util import convert_to_stripe_amount, replace_default_payment_method
from shop.transactions import (
    PaymentFailed,
    payment_success,
    commit_fail_transaction,
)

logger = getLogger("makeradmin")


def raise_from_stripe_invalid_request_error(e: InvalidRequestError) -> Never:
    if "Amount must convert to at least" in str(e) or "Amount must be at least" in str(e):
        raise PaymentFailed("Total amount too small total, least chargable amount is around 5 SEK.")

    raise PaymentFailed(log=f"stripe charge failed: {str(e)}", level=EXCEPTION)


@dataclass
class PaymentAction(DataClassJsonMixin):
    type: PaymentIntentNextActionType
    client_secret: str


class PaymentIntentResult(str, Enum):
    Success = "success"
    RequiresAction = "requires_action"
    Wait = "wait"


@dataclass
class PartialPayment(DataClassJsonMixin):
    type: PaymentIntentResult
    transaction_id: int
    # Payment needs additional actions to complete if this is non-null.
    # If it is None then the payment is complete.
    action_info: Optional[PaymentAction]


def create_action_required_response(transaction: Transaction, payment_intent: PaymentIntent) -> PaymentAction:
    """The payment_intent requires customer action to be confirmed. Create response to client"""

    try:
        next_action_type = PaymentIntentNextActionType(payment_intent.next_action.type)
        if next_action_type == PaymentIntentNextActionType.USE_STRIPE_SDK:
            return PaymentAction(
                type=PaymentIntentNextActionType.USE_STRIPE_SDK,
                client_secret=payment_intent.client_secret,
            )

        elif next_action_type == PaymentIntentNextActionType.REDIRECT_TO_URL:
            raise InternalServerError(log=f"unexpected next_action type, {next_action_type}")

        else:
            raise PaymentFailed(log=f"unknown next_action type, {next_action_type}")

    except Exception:
        # Fail transaction on all known and unknown errors to be safe, we won't charge a failed transaction.
        commit_fail_transaction(transaction)
        logger.info(f"failing transaction {transaction.id}, due to error when processing 3ds card")
        raise


def create_client_response(transaction: Transaction, payment_intent: PaymentIntent) -> Optional[PaymentAction]:
    status = PaymentIntentStatus(payment_intent.status)
    if status == PaymentIntentStatus.REQUIRES_ACTION:
        """Requires further action on client side."""
        if not payment_intent.next_action:
            raise InternalServerError(f"intent next_action is required but missing ({payment_intent.next_action})")
        return create_action_required_response(transaction, payment_intent)

    elif status == PaymentIntentStatus.REQUIRES_CONFIRMATION:
        confirmed_intent = stripe.PaymentIntent.confirm(payment_intent.id)
        assert PaymentIntentStatus(confirmed_intent.status) != PaymentIntentStatus.REQUIRES_CONFIRMATION
        return create_client_response(transaction, confirmed_intent)

    elif status == PaymentIntentStatus.SUCCEEDED:
        payment_success(transaction)
        logger.info(f"succeeded: payment for transaction {transaction.id}, payment_intent id {payment_intent.id}")
        return None

    elif status == PaymentIntentStatus.REQUIRES_PAYMENT_METHOD:
        commit_fail_transaction(transaction)
        logger.info(f"failed: payment for transaction {transaction.id}, payment_intent id {payment_intent.id}")
        raise BadRequest(log=f"payment_intent requires payment method, either no method provided or the payment failed")

    else:
        raise InternalServerError(log=f"unexpected stripe payment_intent status {payment_intent.status}, this is a bug")


def confirm_stripe_payment_intent(transaction_id: int) -> PartialPayment:
    """Called by client after payment_intent next_action has been handled"""
    pending = db_session.query(StripePending).filter_by(transaction_id=transaction_id).one()
    transaction = db_session.query(Transaction).get(transaction_id)
    if not transaction:
        raise BadRequest(f"unknown transaction ({transaction_id})")
    if transaction.status != Transaction.PENDING:
        raise BadRequest(f"transaction ({transaction_id}) is not pending")

    payment_intent = stripe.PaymentIntent.retrieve(pending.stripe_token)
    status = PaymentIntentStatus(payment_intent.status)
    if status == PaymentIntentStatus.CANCELED:
        raise BadRequest(f"unexpected stripe payment intent status {status}")

    try:
        action_info = create_client_response(transaction, payment_intent)
    except CardError as e:
        # Reason can be for example: 'Your card's security code is incorrect'.
        commit_fail_transaction(transaction)
        err = PaymentFailed(log=f"Payment failed: {str(e)}", level=EXCEPTION)
        err.message = e.user_message
        raise err

    if (
        action_info is None
        and payment_intent.setup_future_usage is not None
        and SetupFutureUsage(payment_intent.setup_future_usage) == SetupFutureUsage.OFF_SESSION
    ):
        # We have indicated that this payment method should be used for future payments too.
        # Therefore we make this payment method the default payment method for the customer,
        # to allow it to be used for subscriptions.
        # The customer must have a default payment method so that invoices for a subscription can be charged.

        replace_default_payment_method(payment_intent["customer"], payment_intent["payment_method"])

    return PartialPayment(
        type=PaymentIntentResult.Success if action_info is None else PaymentIntentResult.RequiresAction,
        transaction_id=transaction.id,
        action_info=action_info,
    )


def pay_with_stripe(transaction: Transaction, payment_method_id: str, setup_future_usage: bool) -> None:
    """Handle stripe payment, Returns dict containing data for further processing customer action or None."""

    try:
        member = db_session.query(Member).get(transaction.member_id)
        assert member is not None
        stripe_customer = get_and_sync_stripe_customer(member)
        assert stripe_customer is not None

        payment_intent = stripe.PaymentIntent.create(
            payment_method=payment_method_id,
            amount=convert_to_stripe_amount(transaction.amount),
            currency=CURRENCY,
            customer=stripe_customer.stripe_id,
            description=f"charge for transaction id {transaction.id}",
            confirmation_method="manual",
            confirm=True,
            # One might think that off_session could be set to true to make payments possible without
            # user interaction. Sadly, it seems that most cards require 3d secure verification, which
            # is not possible with off_session payments.
            # Subscriptions may instead email the user to ask them to verify the payment.
            off_session=False,
            setup_future_usage=SetupFutureUsage.OFF_SESSION.value if setup_future_usage else None,
            metadata={
                MakerspaceMetadataKeys.TRANSACTION_IDS.value: transaction.id,
            },
        )

        db_session.add(StripePending(transaction_id=transaction.id, stripe_token=payment_intent.stripe_id))
        db_session.flush()

        logger.info(
            f"created stripe payment_intent for transaction {transaction.id}, payment_intent id {payment_intent.id}"
        )
    except InvalidRequestError as e:
        raise_from_stripe_invalid_request_error(e)
