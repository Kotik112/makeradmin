import React from 'react';
import CategoryPeriods from "../Models/CategoryPeriods";
import CategoryPeriodsInput from "../Components/CategoryPeriodsInput";
import {calculateSpanDiff, filterPeriods} from "../Models/Span";


export default class MembershipPeriodsInput extends React.Component {
    constructor(props) {
        super(props);
        this.unsubscribe = [];
        this.categoryPeriodsList = [
            new CategoryPeriods({category: 'labaccess'}),
            new CategoryPeriods({category: 'membership'}),
            new CategoryPeriods({category: 'special_labaccess'}),
        ];
        this.state = {showHistoric: true, saveDisabled: true};
    }

    canSave() {
        return this.categoryPeriodsList.every(c => c.isValid()) && this.categoryPeriodsList.some(c => c.isDirty());
    }
    
    componentDidMount() {
        this.unsubscribe.push(this.props.spans.subscribe(({items}) => {
            this.categoryPeriodsList.forEach(periods => periods.replace(filterPeriods(items, periods.category)));
        }));
        this.categoryPeriodsList.forEach(cp => {
            this.unsubscribe.push(cp.subscribe(() => this.setState({saveDisabled: !this.canSave()})));
        });
    }

    componentWillUnmount() {
        this.unsubscribe.forEach(u => u());
    }

    render() {
        const {showHistoric, saveDisabled} = this.state;
        const {member_id} = this.props;
        
        const onSave = () => {
            // Important, need to collect spans to delete and add before doing anything, when spans changes
            // subscriptions on spans will start causing changes of category periods.
            const deleteSpans = [];
            const addSpans = [];
            this.categoryPeriodsList.forEach(cp => {
                cp.merge();
                calculateSpanDiff({items: this.props.spans.items, categoryPeriods: cp, member_id, deleteSpans, addSpans});
            });
            // console.info("delete", deleteSpans);
            // console.info("add", addSpans);
        };
        
        return (
            <form className="uk-form" onSubmit={(e) => {e.preventDefault(); onSave(); return false;}}>
                <label className="uk-label" htmlFor="showHistoric">Visa historiska</label>
                <input id="showHistoric" className="uk-checkbox" type="checkbox" checked={showHistoric} onChange={e => this.setState({showHistoric: e.target.checked})}/>
                {this.categoryPeriodsList.map(cp => <CategoryPeriodsInput key={cp.category} categoryPeriods={cp} showHistoric={showHistoric}/>)}
                <button disabled={saveDisabled} className="uk-button uk-button-success uk-float-right"><i className="uk-icon-save"/> Spara</button>
            </form>
        );
    }
}


