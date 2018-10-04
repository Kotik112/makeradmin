import * as _ from "underscore";


// eslint-disable-next-line
export const assert = expression => console.assert(expression);


const utcDateFormat = Intl.DateTimeFormat("sv-SE", {timeZone: "UTC", year: 'numeric', month: 'numeric', day: 'numeric'});


export const formatUtcDate = date => utcDateFormat.format(date);



export const dateToStr = date => {
    if (!_.isEmpty(date)) {
        const options = {
            year: 'numeric', month: 'numeric', day: 'numeric',
            hour12: false
        };
        
        const parsed_date = Date.parse(date);
        
        // If the date was parsed successfully we should update the string
        if (!isNaN(parsed_date)) {
            return new Intl.DateTimeFormat("sv-SE", options).format(parsed_date);
        }
    }
    return "";
};


export const dateTimeToStr = date => {
    if (!_.isEmpty(date)) {
        const options = {
            year: 'numeric', month: 'numeric', day: 'numeric',
            hour: 'numeric', minute: 'numeric', second: 'numeric',
            hour12: false
        };
        
        const parsed_date = Date.parse(date);
        
        // If the date was parsed successfully we should update the string
        if (!isNaN(parsed_date)) {
            return new Intl.DateTimeFormat("sv-SE", options).format(parsed_date);
        }
    }
    return "";
};
