(function () {
    function element(tag, cls, text) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text) node.textContent = text;
        return node;
    }
    window.openPaymentEdit = function (row, payment, piId, shipped) {
        document.querySelectorAll('.payment-edit-row').forEach(function (node) { node.remove(); });
        var editor = element('div', 'payment-edit-row bg-light rounded p-3 mt-2');
        var form = element('form', 'row g-2');
        function field(label, type, value, columns) {
            var col = element('div', columns), caption = element('label', 'form-label small', label);
            var input = element(type === 'textarea' ? 'textarea' : 'input', 'form-control form-control-sm');
            input.id = 'payment-edit-' + payment.id + '-' + type; caption.htmlFor = input.id;
            if (type !== 'textarea') input.type = type;
            input.value = value; input.required = true;
            col.append(caption, input); form.append(col); return input;
        }
        var amount = field('实收金额（原币） *', 'number', Number(payment.amount).toFixed(2), 'col-md-3');
        amount.min = '0.01'; amount.step = '0.01';
        var day = field('实际到账日期 *', 'date', payment.received_on || (payment.registered_at || '').slice(0, 10), 'col-md-3');
        var now = new Date(); day.max = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
        var reason = field('修改原因 *', 'textarea', '', 'col-md-6'); reason.maxLength = 500; reason.rows = 2;
        form.append(element('div', 'col-12 small text-muted', '修改直接生效，并更新相关统计；原流水号、账户、手续费和凭证保留。'));
        if (shipped) form.append(element('div', 'col-12 text-danger small fw-semibold', '该订单已发货。修改后若未付清，将标记异常并保留原发货记录。'));
        var status = element('div', 'col-12 small'); status.setAttribute('role', 'status'); form.append(status);
        var actions = element('div', 'col-12 d-flex gap-2');
        var save = element('button', 'btn btn-sm btn-primary', '保存修改'); save.type = 'submit';
        var cancel = element('button', 'btn btn-sm btn-outline-secondary', '取消'); cancel.type = 'button';
        cancel.onclick = function () { editor.remove(); }; actions.append(save, cancel); form.append(actions);
        form.onsubmit = async function (event) {
            event.preventDefault();
            if (!reason.value.trim()) { reason.focus(); status.textContent = '请填写修改原因。'; return; }
            save.disabled = true; cancel.disabled = true; status.textContent = '正在保存…';
            try {
                var response = await fetch('/api/pi/' + piId + '/payments/' + payment.id + '/edit', {
                    method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
                    body: JSON.stringify({amount: amount.value, received_on: day.value, reason: reason.value.trim(), revision: payment.revision})
                });
                var data = await response.json();
                if (!response.ok) throw Error(data.error || '保存失败，请刷新后重试。');
                if (data.shipping_payment_shortfall) alert(data.message);
                try { sessionStorage.setItem('reopenPaymentPi', String(piId)); } catch (_) {}
                window.location.reload();
            } catch (error) {
                status.className = 'col-12 small text-danger'; status.textContent = error.message;
                save.disabled = false; cancel.disabled = false;
            }
        };
        editor.append(form); row.after(editor); amount.focus();
    };
    window.appendPaymentEdits = function (body, payment) {
        if (!payment.edits || !payment.edits.length) return;
        var details = element('details', 'payment-edit-history small text-muted mt-2');
        details.append(element('summary', '', '修改记录（' + payment.edits.length + '）'));
        payment.edits.forEach(function (edit) {
            details.append(element('div', 'py-1 border-bottom', edit.actor + ' · ' + edit.time + '：金额 ' + edit.before_amount + ' → ' + edit.after_amount + '；到账日期 ' + (edit.before_date || '未填写') + ' → ' + edit.after_date + '；原因：' + edit.reason));
        }); body.append(details);
    };
    document.addEventListener('DOMContentLoaded', function () {
        try {
            var piId = sessionStorage.getItem('reopenPaymentPi'); sessionStorage.removeItem('reopenPaymentPi');
            if (/^\d+$/.test(piId || '') && window.viewPayments) viewPayments(Number(piId));
        } catch (_) {}
    });
})();
