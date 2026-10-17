document.addEventListener('DOMContentLoaded', function () {
    const select = document.getElementById('contact_id');
    const customer = document.getElementById('customer_id');
    if (!select || !customer) return;
    const summary = document.getElementById('piContactSummary');
    const snapshot = JSON.parse(select.dataset.snapshot || '{}');
    let entries = [], revision = 0;
    function describe() {
        const contact = select.value === '__snapshot__' ? snapshot : entries.find(c => c.id === select.value);
        summary.textContent = contact ? [contact.name, contact.position, contact.phone, contact.whatsapp && 'WhatsApp: ' + contact.whatsapp, contact.email, contact.wechat && '微信: ' + contact.wechat].filter(Boolean).join(' · ') || '本单未填写联系信息' : '此客户暂无联系人，可在客户资料中添加。';
    }
    async function load(initial) {
        const current = ++revision;
        const wanted = initial ? select.dataset.selected : '';
        select.replaceChildren(new Option('正在读取联系人……', ''));
        select.setCustomValidity('请等待联系人加载完成。');
        summary.textContent = '';
        if (!customer.value) { select.replaceChildren(new Option('请先选择客户', '')); select.setCustomValidity(''); return; }
        try {
            const response = await fetch('/api/customers/' + encodeURIComponent(customer.value) + '/contacts');
            if (!response.ok) throw new Error('联系人读取失败，请重新选择客户。');
            const data = await response.json();
            if (current !== revision) return;
            entries = data.contacts;
            select.replaceChildren();
            if (customer.value === select.dataset.originalCustomer) select.add(new Option('保留本单原联系人（历史快照）', '__snapshot__'));
            entries.forEach(c => select.add(new Option((c.name || c.phone || c.email || '未命名联系人') + (c.is_default ? '（默认）' : ''), c.id)));
            if (!select.options.length) select.add(new Option('暂无联系人', ''));
            const fallback = entries.find(c => c.is_default) || entries[0];
            select.value = Array.from(select.options).some(o => o.value === wanted) ? wanted : (fallback ? fallback.id : select.options[0].value);
            select.setCustomValidity(''); describe();
        } catch (error) { if (current === revision) { select.setCustomValidity(error.message); summary.textContent = error.message; } }
    }
    customer.addEventListener('change', () => load(false));
    select.addEventListener('change', describe);
    load(true);
});
