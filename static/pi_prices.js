window.PIPrices = {
    price: function(value) { return Math.round((Number(value) + Number.EPSILON) * 1000) / 1000; },
    amount: function(price, quantity) {
        // Integer thousandths keep half-cent rounding consistent with saved PI rows.
        var thousandths = Math.round((Number(price) + Number.EPSILON) * 1000);
        return Math.round(thousandths * Number(quantity) / 10) / 100;
    }
};
