document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('paymentForm');
    if (!form) return;
    const reference = document.getElementById('payOrderNo');
    const amount = document.getElementById('payAmount');
    const submit = form.querySelector('[type="submit"]');
    const referenceHelp = document.createElement('div');
    const amountHelp = document.createElement('div');
    referenceHelp.className = amountHelp.className = 'small mt-1';
    referenceHelp.setAttribute('aria-live', 'polite');
    amountHelp.setAttribute('aria-live', 'polite');
    reference.after(referenceHelp);
    amount.closest('.input-group').after(amountHelp);
    let piId, remaining = null, checked = null, duplicate = false, pending = false, failed = false, revision = 0, timer;
    function render() {
        const value = Number(amount.value);
        const over = remaining !== null && Math.round(value * 100) > Math.round(remaining * 100);
        amount.classList.toggle('is-invalid', over);
        amount.setAttribute('aria-invalid', String(over));
        amountHelp.className = 'small mt-1 ' + (over ? 'text-danger' : 'text-muted');
        amountHelp.textContent = remaining === null ? '正在读取剩余应收金额……' :
            (over ? '实收金额超过剩余应收，最多可登记 ' : '剩余应收：') + remaining.toFixed(2) + ' ' + document.getElementById('payCurrency').textContent;
        reference.classList.toggle('is-invalid', duplicate || failed);
        reference.setAttribute('aria-invalid', String(duplicate || failed));
        referenceHelp.className = 'small mt-1 ' + (duplicate || failed ? 'text-danger' : 'text-muted');
        referenceHelp.textContent = pending ? '正在核对流水号……' : failed ? '核对失败，请点击重试。' : duplicate ? '该回款流水号已登记，请核对并更换，不能重复入账。' : '';
        submit.disabled = pending || failed || duplicate || remaining === null || over || !reference.value.trim() || checked !== reference.value || !amount.value || value <= 0 || !Number.isFinite(value);
        return !submit.disabled;
    }
    async function check() {
        clearTimeout(timer);
        const ticket = ++revision, target = piId, value = reference.value;
        if (!target) return;
        pending = true; failed = false; checked = null; render();
        try {
            const response = await fetch('/api/pi/' + target + '/payment-check', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({order_no:value})
            });
            if (!response.ok) throw new Error();
            const data = await response.json();
            if (ticket !== revision) return;
            remaining = data.remaining; duplicate = data.duplicate; checked = value;
        } catch (_) { if (ticket === revision) failed = true; }
        finally { if (ticket === revision) { pending = false; render(); } }
    }
    reference.addEventListener('input', function () {
        ++revision; checked = null; duplicate = false; pending = true; failed = false;
        clearTimeout(timer); render(); timer = setTimeout(check, 350);
    });
    reference.addEventListener('blur', check);
    referenceHelp.addEventListener('click', function () { if (failed) check(); });
    amount.addEventListener('input', render);
    amount.addEventListener('change', render);
    window.paymentLiveCheck = {
        amount:render, valid:render,
        reset:function(id) { ++revision; clearTimeout(timer); piId=id; remaining=null; checked=null; duplicate=false; failed=false; check(); }
    };
});
