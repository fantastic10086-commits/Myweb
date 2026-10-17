// Shared compact order-information layout for creating and editing a PI.
document.addEventListener('DOMContentLoaded', function () {
    const grid = document.querySelector('.order-required-grid, .pi-edit-info');
    if (!grid) return;
    grid.classList.add('pi-order-grid');
    const fields = [
        ['customer_id', 3], ['contact_id', 3], ['pi_salesperson', 3], ['issue_date', 3],
        ['account_select', 6], ['currency_select', 3], ['exchange_rate', 3],
        ['price_terms', 4], ['payment_terms', 4], ['delivery_time', 4],
        ['shipping_address', 4], ['notes', 4], ['customer_notes_display', 4]
    ];
    fields.forEach(([id, span]) => {
        const input = document.getElementById(id);
        const field = input && input.closest('.mb-3');
        if (!field || !grid.contains(field)) return;
        field.style.setProperty('--field-span', span);
        grid.appendChild(field);
        // Keep instructions available by keyboard and click without stretching rows.
        const help = Array.from(field.children).find(el => el.matches('.form-text, small') && el.id !== 'piContactSummary');
        const label = field.querySelector('.form-label');
        if (help && label) {
            const tip = document.createElement('details');
            tip.className = 'pi-field-help';
            const toggle = document.createElement('summary');
            toggle.textContent = 'ⓘ';
            toggle.setAttribute('aria-label', label.textContent.trim() + '说明');
            tip.append(toggle, help);
            label.appendChild(tip);
        }
        if (input.tagName === 'TEXTAREA') input.rows = 2;
    });
    // Preserve the existing editor's bank snapshot control in an optional disclosure.
    const bank = document.getElementById('bank_info');
    const bankField = bank && bank.closest('.mb-3');
    if (bankField && grid.contains(bankField)) {
        const disclosure = document.createElement('details');
        disclosure.className = 'pi-bank-details';
        const heading = document.createElement('summary');
        heading.textContent = '银行资料（需要时展开）';
        grid.appendChild(disclosure);
        disclosure.append(heading, bankField);
    }
    const customerNote = document.getElementById('customer_notes_display');
    function normalizeNote() {
        if (customerNote && (!customerNote.textContent.trim() || customerNote.textContent.trim() === '—')) customerNote.textContent = '无';
    }
    normalizeNote();
    if (customerNote) new MutationObserver(normalizeNote).observe(customerNote, {childList:true});
    const customer = document.getElementById('customer_id');
    const contact = document.getElementById('contact_id');
    const trade = document.getElementById('price_terms');
    const currency = document.getElementById('currency_select');
    const heading = document.querySelector('#editOrderSummary, #orderInformation summary > span');
    function updateSummary() {
        const parts = [];
        const option = customer.selectedOptions[0];
        if (customer.value && option) parts.push(option.dataset.name || option.textContent.trim());
        if (contact.value === '__snapshot__') {
            const snapshot = JSON.parse(contact.dataset.snapshot || '{}');
            if (snapshot.name) parts.push(snapshot.name);
        } else if (contact.value && contact.selectedOptions[0]) parts.push(contact.selectedOptions[0].textContent.replace('（默认）', ''));
        if (trade.value.trim()) parts.push(trade.value.trim());
        if (currency.value) parts.push(currency.value);
        if (heading) heading.textContent = parts.join(' · ');
    }
    [customer, contact, trade, currency].forEach(el => {
        el.addEventListener('change', updateSummary);
        el.addEventListener('input', updateSummary);
    });
    new MutationObserver(updateSummary).observe(contact, {childList:true});
    updateSummary();
});
