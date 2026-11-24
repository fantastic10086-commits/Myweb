(function () {
    function element(tag, cls, text) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function receipt(payment) {
        if (!payment.has_attachment) return element('span', 'small text-muted', '凭证：无');
        var url = '/payments/' + payment.id + '/attachment';
        var button = element('button', 'payment-receipt');
        button.type = 'button';
        button.setAttribute('aria-label', '放大回款凭证');
        button.setAttribute('aria-expanded', 'false');
        var image = element('img');
        image.alt = '回款凭证'; image.loading = 'lazy'; image.decoding = 'async';
        var caption = element('span', '', '凭证 · 点击放大');
        image.onerror = function () { image.hidden = true; caption.textContent = '图片加载失败，点击重试'; };
        image.src = url + '?thumbnail=1';
        button.append(image, caption);
        button.onclick = function () {
            var expanded = button.classList.toggle('is-expanded');
            image.hidden = false;
            image.src = url + (expanded ? '' : '?thumbnail=1');
            caption.textContent = expanded ? '点击收起凭证' : '凭证 · 点击放大';
            button.setAttribute('aria-expanded', String(expanded));
            button.setAttribute('aria-label', expanded ? '收起回款凭证' : '放大回款凭证');
        };
        return button;
    }

    window.renderPaymentHistory = function (history, data, piId, symbol) {
        history.replaceChildren();
        if (data.shipping_payment_shortfall) {
            history.append(element('div', 'alert alert-danger py-2', '异常：订单已发货，但当前回款未付清。原发货记录已保留，请及时核对。'));
        }
        if (!data.payments.length) return;
        history.append(element('h6', '', '历史记录'));
        data.payments.forEach(function (payment, index) {
            var card = element('article', 'payment-history-card');
            card.setAttribute('aria-label', '第 ' + (index + 1) + ' 笔回款');
            var main = element('div');
            var header = element('div', 'payment-history-header');
            header.append(element('strong', '', '#' + (index + 1) + '　实收金额：' + symbol + Number(payment.amount).toFixed(2)));
            var actions = element('div', 'payment-history-actions');
            var edit = element('button', 'btn btn-sm btn-outline-primary', '编辑');
            edit.type = 'button';
            edit.onclick = function () { openPaymentEdit(main, payment, piId, data.shipping_completed); };
            var remove = element('button', 'btn btn-sm btn-outline-danger', '移入回收站');
            remove.type = 'button';
            remove.onclick = function () {
                var value = prompt('请输入回款流水号，将其移入回收站：\n\n' + payment.order_no);
                if (value === null) return;
                var form = element('form'); form.method = 'post';
                form.action = '/pi/' + piId + '/payment/' + payment.id + '/delete';
                var csrf = element('input'); csrf.type = 'hidden'; csrf.name = 'csrf_token';
                csrf.value = document.querySelector('meta[name="csrf-token"]').content;
                var confirmation = element('input'); confirmation.type = 'hidden';
                confirmation.name = 'confirm_value'; confirmation.value = value;
                form.append(csrf, confirmation); document.body.append(form); form.submit();
            };
            actions.append(edit, remove); header.append(actions); main.append(header);
            var content = element('div', 'payment-history-content');
            var fields = element('dl', 'payment-history-fields');
            [
                ['流水号', payment.order_no || '—', 'payment-history-reference'],
                ['实际到账日期', payment.received_on || '未填写'],
                ['手续费', symbol + Number(payment.fee || 0).toFixed(2)],
                ['到账账户', payment.receiving_account_name || '历史记录未填写', 'payment-history-account'],
                ['登记时间', payment.registered_at || payment.created_at || '—']
            ].forEach(function (field) {
                var item = element('div', field[2]);
                item.append(element('dt', '', field[0]), element('dd', '', field[1]));
                fields.append(item);
            });
            content.append(fields, receipt(payment)); main.append(content);
            var note = element('div', 'payment-history-note');
            note.append(element('span', 'payment-history-note-label', '备注'), element('span', '', payment.note || '—'));
            main.append(note); card.append(main);
            appendPaymentEdits(card, payment); history.append(card);
        });
    };
})();
