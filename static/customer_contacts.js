(function () {
    const hidden = document.getElementById('contactsJson');
    if (!hidden) return;
    let contacts;
    try { contacts = JSON.parse(hidden.value); } catch (_) { contacts = []; }
    if (!Array.isArray(contacts)) contacts = [];
    const rows = document.getElementById('contactEditorRows');
    const fields = [['name', '姓名', 100], ['position', '职位', 100], ['phone', '电话', 50], ['whatsapp', 'WhatsApp', 50], ['email', '邮箱', 200], ['wechat', '微信', 100], ['note', '备注', 1000]];
    function sync() { hidden.value = JSON.stringify(contacts); }
    function render() {
        rows.replaceChildren();
        contacts.forEach((contact, index) => {
            const box = document.createElement('div'); box.className = 'border rounded p-3 mb-2';
            const bar = document.createElement('div'); bar.className = 'd-flex justify-content-between mb-2';
            const label = document.createElement('label'); label.className = 'form-check-label';
            const radio = document.createElement('input'); radio.type = 'radio'; radio.name = 'default_contact'; radio.className = 'form-check-input me-2'; radio.checked = !!contact.is_default;
            radio.addEventListener('change', () => { contacts.forEach(c => c.is_default = c === contact); sync(); });
            label.append(radio, document.createTextNode('默认联系人')); bar.append(label);
            const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'btn btn-sm btn-outline-danger'; remove.textContent = '删除联系人';
            remove.addEventListener('click', () => { if (!confirm('从客户资料删除此联系人？历史 PI 中的联系人信息会保留。')) return; contacts.splice(index, 1); if (contacts.length && !contacts.some(c => c.is_default)) contacts[0].is_default = true; render(); });
            bar.append(remove); box.append(bar);
            const grid = document.createElement('div'); grid.className = 'row g-2';
            fields.forEach(([key, title, limit]) => {
                const col = document.createElement('div'); col.className = key === 'note' ? 'col-12' : 'col-md-4';
                const caption = document.createElement('label'); caption.className = 'form-label small mb-1'; caption.textContent = title;
                const input = document.createElement(key === 'note' ? 'textarea' : 'input'); input.className = 'form-control form-control-sm'; input.maxLength = limit; input.value = contact[key] || ''; input.id = 'contact-' + index + '-' + key; caption.htmlFor = input.id;
                if (key === 'email') input.type = 'email';
                input.addEventListener('input', () => { contact[key] = input.value; sync(); });
                col.append(caption, input); grid.append(col);
            });
            box.append(grid); rows.append(box);
        });
        sync();
    }
    document.getElementById('addContact').addEventListener('click', () => {
        if (contacts.length >= 50) { alert('每个客户最多保存 50 位联系人。'); return; }
        contacts.push({id: crypto.randomUUID(), is_default: !contacts.length}); render();
    });
    render();
})();
