// Legacy element names remain stable for saved EUR drafts.
window.piUsdFactor = function() {
    const c = typeof getCurrency === 'function' ? getCurrency() : 'USD';
    if (c !== 'USD' && c !== 'RMB') return 1 / (Number(document.getElementById('eur_usd_rate').value) || 1);
    return c === 'RMB' ? getBusinessRate() : 1;
};
document.addEventListener('DOMContentLoaded', function() {
    const panel = document.getElementById('eur-rate-fields'); if (!panel) return;
    const currency = document.getElementById('currency_select'), usd = document.getElementById('eur_usd_rate'), rmb = document.getElementById('eur_rmb_rate');
    const status = document.getElementById('eur-rate-status'), button = document.getElementById('fetch-eur-rates');
    const genericUsd = document.getElementById('currency_usd_rate'), genericRmb = document.getElementById('currency_rmb_rate');
    let lastCurrency = currency.value, requestId = 0, pending = '';
    function custom() { return currency.value && !['USD','RMB','EUR'].includes(currency.value); }
    function sync() { genericUsd.value = custom() ? usd.value : ''; genericRmb.value = custom() ? rmb.value : ''; }
    function recalc() { sync(); document.dispatchEvent(new Event('eur-rates-updated')); if (typeof repriceForCurrency === 'function') repriceForCurrency(); }
    function display() {
        const foreign = currency.value && !['USD','RMB'].includes(currency.value);
        panel.style.display = foreign ? '' : 'none'; usd.required = rmb.required = !!foreign;
        panel.querySelectorAll('.rate-currency').forEach(el => { el.textContent = currency.value; });
    }
    async function fetchRates() {
        const code = currency.value, id = ++requestId; pending = code; button.disabled = true; status.textContent = '正在获取参考汇率…';
        try {
            const response = await fetch('/api/exchange-rates/currency/' + encodeURIComponent(code));
            const data = await response.json(); if (!response.ok) throw Error(data.error);
            if (id !== requestId || currency.value !== code) return;
            usd.value = data.currency_usd_rate; rmb.value = data.currency_rmb_rate;
            document.getElementById('fx_reference_date').value = data.fx_reference_date;
            document.getElementById('fx_source').value = data.fx_source;
            status.textContent = data.fx_source + ' · 参考日期 ' + data.fx_reference_date + ' · 保存后固定'; recalc();
        } catch (e) { if (id === requestId) status.textContent = e.message || '获取失败，请手动填写。'; }
        finally { if (id === requestId) { pending = ''; button.disabled = false; } }
    }
    window.updateEurCurrency = function() {
        if (currency.value !== lastCurrency) {
            lastCurrency = currency.value; requestId++; pending = ''; button.disabled = false;
            usd.value = rmb.value = ''; document.getElementById('fx_reference_date').value = '';
            document.getElementById('fx_source').value = ''; status.textContent = ''; sync();
        }
        display(); sync();
        if (currency.value && !['USD','RMB'].includes(currency.value) && !usd.value && !rmb.value && pending !== currency.value) fetchRates();
    };
    currency.addEventListener('change', window.updateEurCurrency);
    [usd,rmb].forEach(el => el.addEventListener('input', function() {
        requestId++; pending = ''; button.disabled = false; document.getElementById('fx_source').value = '手动填写/调整';
        status.textContent = '手动汇率，随本单保存'; recalc();
    }));
    button.addEventListener('click', fetchRates); usd.form.addEventListener('submit', sync, true); display(); sync();
    const source = document.getElementById('fx_source').value, date = document.getElementById('fx_reference_date').value;
    if (source) status.textContent = source + (date ? ' · 参考日期 ' + date : '') + ' · 本单已保存';
    window.updateEurCurrency();
});
