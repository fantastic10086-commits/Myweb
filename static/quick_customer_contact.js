window.resetQuickCustomerContact = function () {
    ['position', 'phone', 'email', 'whatsapp', 'wechat', 'note'].forEach(function(key) {
        document.getElementById('qa_cust_' + key).value = '';
    });
    document.getElementById('qaContactDetails').open = false;
};
window.appendQuickCustomerContact = function (form) {
    var contact = {name: document.getElementById('qa_cust_contact').value.trim(), is_default: true};
    if (!contact.name) {
        document.getElementById('qa_cust_contact').focus();
        return '请填写联系人姓名。';
    }
    var invalid = false;
    ['position', 'phone', 'email', 'whatsapp', 'wechat', 'note'].forEach(function(key) {
        var input = document.getElementById('qa_cust_' + key);
        contact[key] = input.value.trim();
        if (!input.checkValidity()) {
            document.getElementById('qaContactDetails').open = true;
            input.reportValidity();
            invalid = true;
        }
    });
    if (invalid) return '请检查联系人其他信息。';
    form.append('contacts_json', JSON.stringify([contact]));
    return '';
};
