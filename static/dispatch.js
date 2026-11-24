// Shared by the PI list dialog and the full order dispatch page.
var currentExpensePiId = null;
var currentExpensePiNumber = '';
var currentCustomsPiId = null;
var currentShippingPiId = null;
var dispatchChanged = false;
document.getElementById('customsModal').addEventListener('hidden.bs.modal', function() {
    if (dispatchChanged) window.location.reload();
});
var dispatchDirty = false, dispatchBusy = false, dispatchPending = null;
var dispatchVersion = null, dispatchShipping = null, dispatchEditing = false;
var dispatchBatchId = null, dispatchNewBatch = false, dispatchBatch = null;
var dispatchModal = document.getElementById('customsModal');
var dispatchPage = dispatchModal.dataset.page === 'true';
var canDeleteExpense = dispatchModal.dataset.admin === 'true';
var canRevertShipping = canDeleteExpense;
var dispatchUploading = false;
dispatchModal.addEventListener('input', function() { dispatchDirty = true; });
dispatchModal.addEventListener('change', function() { dispatchDirty = true; });
dispatchModal.addEventListener('hide.bs.modal', function(event) {
    if (dispatchBusy || dispatchUploading || (dispatchDirty && !confirm('有尚未保存的信息，确定关闭吗？'))) event.preventDefault();
});
window.addEventListener('beforeunload', function(event) {
    if ((dispatchDirty || dispatchBusy || dispatchPending || dispatchUploading) && (dispatchPage || dispatchModal.classList.contains('show'))) { event.preventDefault(); event.returnValue = ''; }
});
function updateDispatchButtons() {
    var ready = dispatchShipping && !document.getElementById('customsFields').disabled;
    var shippingTab = document.getElementById('dispatchShippingTab').classList.contains('active');
    document.getElementById('dispatchInfoBtn').disabled = !ready || dispatchBusy;
    document.getElementById('dispatchNextBtn').classList.toggle('d-none', shippingTab);
    document.getElementById('dispatchNextBtn').disabled = !ready || dispatchBusy;
    var unsent = !dispatchBatch || dispatchBatch.status === 'draft';
    document.getElementById('shippingSaveBtn').classList.toggle('d-none', !shippingTab || !dispatchShipping || !unsent || dispatchShipping.shipping_paused);
    document.getElementById('shippingSaveBtn').textContent = document.getElementById('shippingFinalBatch').checked ? '确认发货完成' : '登记本批发货';
    document.getElementById('shippingAddBatchBtn').disabled = !ready || dispatchBusy || !!dispatchPending || dispatchShipping.shipping_paused;
    document.getElementById('shippingFinalBatch').disabled = dispatchBusy || !!dispatchPending;

    document.getElementById('shippingSaveBtn').disabled = !ready || dispatchBusy || !dispatchShipping.can_ship || !dispatchShipping.expense_count;
    var noExpensesBtn = document.getElementById('dispatchNoExpensesBtn');
    noExpensesBtn.disabled = !ready || dispatchBusy || !!dispatchPending || !!dispatchShipping.expense_count;
    noExpensesBtn.textContent = dispatchShipping && dispatchShipping.no_expenses_confirmed ? '已确认无费用' : '确认无费用';
    noExpensesBtn.title = dispatchShipping && dispatchShipping.expense_count ? '已有登记记录，无需重复确认' : '保存一条 0 元的无费用确认记录';
}
['Forwarder', 'Expenses', 'Shipping'].forEach(function(name) {
    var tab = document.getElementById('dispatch' + name + 'Tab');
    tab.addEventListener('show.bs.tab', function(event) {
        if (dispatchBusy || dispatchPending) { event.preventDefault(); return; }
        if (name !== 'Shipping') return;
        if (dispatchShipping && (dispatchShipping.shipped_batch_count || dispatchShipping.shipping_completed || dispatchShipping.shipping_paused)) return;
        if (!dispatchShipping || !dispatchShipping.forwarder_ready || !dispatchShipping.expense_count) {
            event.preventDefault();
            document.getElementById('dispatchSaveMessage').textContent = !dispatchShipping || !dispatchShipping.forwarder_ready
                ? '请先保存货代和报关情况，再进行下一步。'
                : '请先保存费用记录，或点击「确认无费用」。';
        }
    });
    tab.addEventListener('shown.bs.tab', function() {
        updateDispatchButtons();
        resetDispatchScroll();
        if (dispatchPage) {
            var url = new URL(location.href); url.searchParams.set('tab', name.toLowerCase());
            history.replaceState(null, '', url);
        }
    });
});
function editShippingInformation() {
    if (!dispatchShipping || dispatchShipping.shipping_paused || dispatchBusy || dispatchPending) return;
    dispatchEditing = true;
    document.getElementById('shippingFields').disabled = false;
    document.getElementById('shippingEditBtn').classList.add('d-none');
    document.getElementById('shippingDate').focus();
    document.getElementById('dispatchSaveMessage').textContent = '修改后点击“保存信息”，保留本批及整单的发货状态';
}
function addDispatchExpenseRow() {
    if (dispatchBusy || dispatchPending) return;
    var row = document.createElement('div');
    row.className = 'dispatch-expense border-top pt-2 mt-2';
    row.innerHTML = '<div class="row g-2"><div class="col-md-4"><label class="small">费用类别</label><select class="form-select form-select-sm" data-field="category"></select></div><div class="col-md-3"><label class="small">金额（RMB）</label><input type="number" min="0" step="0.01" class="form-control form-control-sm" data-field="amount" placeholder="无费用填 0"></div><div class="col-md-5"><label class="small">备注</label><input class="form-control form-control-sm" maxlength="500" data-field="note"></div></div><div class="d-flex gap-2 mt-2"><input aria-label="费用附件" type="file" class="form-control form-control-sm" accept="image/jpeg,image/png,image/webp,image/gif" data-field="attachment"><button type="button" class="btn btn-sm btn-outline-danger">移除</button></div>';
    row.querySelector('select').innerHTML = document.getElementById('exp_category').innerHTML;
    row.querySelector('button').onclick = function() { row.remove(); dispatchDirty = true; };
    document.getElementById('extraExpenseRows').appendChild(row);
    dispatchDirty = true;
}
function dispatchLock(locked) {
    // Freeze values while saving, including uncertain network outcomes.
    dispatchModal.querySelector('.modal-body').inert = locked;
}
async function saveDispatch(complete, next, confirmNoExpenses) {
    if (dispatchBusy || !dispatchShipping) return;
    var form, nextTab = '';
    try {
        if (dispatchPending) {
            form = dispatchPending;
        } else {
            var selected = document.querySelector('input[name="customs_required"]:checked');
            var data = {
                token: crypto.randomUUID(), version: dispatchVersion, action: confirmNoExpenses ? 'confirm_no_expenses' : (complete ? 'complete' : (next ? 'next' : 'save')),
                step: document.querySelector('#customsModal [role="tab"].active').id.replace('dispatch', '').replace('Tab', '').toLowerCase(),
                freight_forwarder: document.getElementById('customsForwarder').value,
                customs_required: selected ? selected.value === 'true' : null,
                customs_note: document.getElementById('customsNote').value.trim(),
                no_expenses: false,
                edit_shipping: dispatchEditing && document.getElementById('dispatchShippingTab').classList.contains('active'),
                batch_id: dispatchBatchId, new_batch: dispatchNewBatch,
                final_batch: document.getElementById('shippingFinalBatch').checked,
                shipping_date: document.getElementById('shippingDate').value,
                tracking_no: document.getElementById('shippingTrackingNo').value.trim(),
                shipping_note: document.getElementById('shippingRecordNote').value.trim(), expenses: []
            };
            if ((complete || next) && (!data.freight_forwarder || data.customs_required === null)) { showDispatchTab('Forwarder'); throw new Error('请先选择货代和是否正式报关，再进行下一步。'); }
            if (complete && !dispatchShipping.expense_count) { showDispatchTab('Expenses'); throw new Error('请先保存费用记录，或点击「确认无费用」。'); }
            if (complete && !data.shipping_date) { showDispatchTab('Shipping'); throw new Error('确认发货前请填写发货日期。'); }
            form = new FormData();
            var rows = [{category: document.getElementById('exp_category'), amount: document.getElementById('exp_amount'), note: document.getElementById('exp_note'), attachment: document.getElementById('exp_attachment')}];
            document.querySelectorAll('.dispatch-expense').forEach(function(row) {
                var fields = {}; ['category', 'amount', 'note', 'attachment'].forEach(function(key) { fields[key] = row.querySelector('[data-field="' + key + '"]'); }); rows.push(fields);
            });
            rows.forEach(function(row) {
                var file = row.attachment.files[0];
                if (!row.category.value && !row.amount.value && !row.note.value.trim() && !file) return;
                if (confirmNoExpenses) throw new Error('正在填写费用，请先核对或清空费用输入，再确认无费用。');
                if (!row.category.value || row.amount.value.trim() === '' || !Number.isFinite(Number(row.amount.value)) || Number(row.amount.value) < 0) { showDispatchTab('Expenses'); throw new Error('请完整填写每笔费用的类别和金额，无费用时明确填写 0。'); }
                if (file && file.size > 12 * 1024 * 1024) throw new Error('每张费用图片最大 12 MB。');
                if (file) form.append('expense_attachment_' + data.expenses.length, file);
                data.expenses.push({category: row.category.value, amount: row.amount.value, note: row.note.value.trim()});
            });
            if (data.step === 'expenses' && !confirmNoExpenses && !dispatchShipping.expense_count && !data.expenses.length) throw new Error('请先登记一条费用记录，或点击「确认无费用」。');
            if (data.edit_shipping && shippingImageFile) form.append('shipping_attachment', shippingImageFile, shippingImageFile.name || 'clipboard.png');
            var totalBytes = 0;
            for (var item of form.values()) { if (item instanceof Blob) totalBytes += item.size; }
            if (totalBytes > 30 * 1024 * 1024) throw new Error('本次图片合计不能超过 30 MB，请压缩图片或分次保存费用。');
            form.append('payload', JSON.stringify(data));
            dispatchPending = form;
        }
        dispatchBusy = true;
        dispatchLock(true);
        updateDispatchButtons();
        document.getElementById('dispatchSaveMessage').textContent = '正在保存……';
        var response = await fetch('/api/pi/' + currentCustomsPiId + '/dispatch', {method:'POST', body:form});
        if (response.status >= 400 && response.status < 500) dispatchPending = null;
        var result;
        try { result = await response.json(); } catch (parseError) { throw new Error(response.status === 413 ? '图片合计过大，请减少图片后重试。' : '服务器未返回有效结果，请重试。'); }
        if (!response.ok || !result.success) {
            if (response.status < 500) dispatchPending = null;
            throw new Error(result.error || '保存失败，请检查输入。');
        }
        var savedAction = JSON.parse(form.get('payload'));
        dispatchPending = null;
        dispatchChanged = true;
        dispatchDirty = false;
        setShippingImage(null);
        renderShippingRecord(result, savedAction.new_batch ? 'latest' : savedAction.batch_id);
        document.getElementById('extraExpenseRows').replaceChildren();
        await openExpense(currentCustomsPiId, document.getElementById('customsPINumber').textContent);
        document.getElementById('customsDocumentsBtn').classList.toggle('d-none', !document.getElementById('customsRequiredYes').checked);
        document.getElementById('customsRecordMeta').textContent = '信息已保存。';
        document.getElementById('dispatchSaveMessage').textContent = savedAction.action === 'confirm_no_expenses'
            ? '已确认无费用产生，可点击下一步'
            : (result.shipping_completed ? '已保存 · 发货完成' : (result.shipped_batch_count ? '已保存 · 部分发货，整单尚未发完' : '信息已保存 · 尚未确认发货'));
        document.getElementById('shippingModalError').classList.add('d-none');
        if (savedAction.action === 'next') nextTab = savedAction.step === 'forwarder' ? 'Expenses' : 'Shipping';
    } catch (error) {
        document.getElementById('dispatchSaveMessage').textContent = dispatchPending
            ? '网络结果未确认，请再次点击保存重试；不会重复登记。'
            : error.message;
    } finally {
        dispatchBusy = false;
        dispatchLock(!!dispatchPending);
        updateDispatchButtons();
    }
    if (nextTab) showDispatchTab(nextTab);
}
var expenseAttachmentPreviewUrl = '';
function shippingError(message) {
    var box = document.getElementById('shippingModalError');
    box.textContent = message;
    box.classList.remove('d-none');
}
function localToday() {
    var now = new Date();
    var offset = now.getTimezoneOffset() * 60000;
    return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}
var shippingImageFile = null;
var shippingImageObjectUrl = null;
function setShippingImage(file) {
    if (file && (!/^image\/(jpeg|png|webp|gif)$/.test(file.type) || file.size > 12 * 1024 * 1024)) {
        shippingError('请选择 JPG、PNG、WebP 或 GIF 图片，最大 12 MB。');
        document.getElementById('shippingAttachment').value = '';
        return;
    }
    if (shippingImageObjectUrl) URL.revokeObjectURL(shippingImageObjectUrl);
    shippingImageFile = file;
    shippingImageObjectUrl = file ? URL.createObjectURL(file) : null;
    var img = document.getElementById('shippingImagePreview');
    img.classList.toggle('d-none', !file);
    if (file) img.src = shippingImageObjectUrl;
    else { img.removeAttribute('src'); document.getElementById('shippingAttachment').value = ''; }
}
document.getElementById('shippingAttachment').addEventListener('change', function() {
    setShippingImage(this.files[0] || null);
});
document.getElementById('shippingSection').addEventListener('paste', function(event) {
    if (document.getElementById('shippingFields').disabled) return;
    var items = (event.clipboardData || {}).items || [];
    for (var i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image/') === 0) {
            event.preventDefault();
            setShippingImage(items[i].getAsFile());
            dispatchDirty = true;
            break;
        }
    }
});
function renderShippingRecord(data, preferred) {
    dispatchShipping = data;
    dispatchVersion = data.version;
    var status = document.getElementById('dispatchPageStatus');
    if (status) {
        status.textContent = data.shipping_paused ? '发货已暂停' : (data.shipping_completed ? '整单发货完成' : (data.shipped_batch_count ? '部分发货 · 已发 ' + data.shipped_batch_count + ' 批' : '尚未发货'));
        status.className = 'badge ' + (data.shipping_completed ? 'bg-success' : 'bg-primary');
    }
    var batches = data.batches || [];
    var active = batches.filter(function(b) { return b.status !== 'cancelled'; });
    var selected = preferred !== 'latest' ? batches.find(function(b) { return b.id === preferred; }) : null;
    selected = selected || active[active.length - 1] || null;
    renderShippingBatchHistory();
    selectShippingBatch(selected, false);
}
function renderShippingBatchHistory() {
    var data = dispatchShipping, history = document.getElementById('shippingBatchHistory');
    history.replaceChildren();
    document.getElementById('shippingBatchSummary').textContent = '已发 ' + data.shipped_batch_count + ' 批 · ' + (data.shipping_paused ? '发货已暂停' : (data.shipping_completed ? '整单发货完成' : (data.shipped_batch_count ? '部分发货' : '尚未发货')));
    (data.batches || []).forEach(function(batch) {
        var row = document.createElement('div');
        row.className = 'dispatch-batch-row d-flex align-items-center gap-2 border-bottom py-2 small';
        row.dataset.batchId = batch.id;
        var title = document.createElement('strong'); title.className = 'text-nowrap'; title.textContent = '第 ' + batch.batch_no + ' 批';
        var info = document.createElement('span'); info.className = 'flex-grow-1 text-break';
        info.textContent = (batch.shipping_date || '日期待填') + ' · ' + (batch.tracking_no || '未填物流单号');
        var status = document.createElement('span'); status.className = 'badge ' + (batch.status === 'shipped' ? 'bg-success' : 'bg-secondary');
        status.textContent = batch.status === 'shipped' ? (batch.is_final ? '最后一批' : '已发货') : (batch.status === 'draft' ? '草稿' : '已撤销');
        var button = document.createElement('button'); button.type = 'button'; button.className = 'btn btn-sm btn-outline-primary text-nowrap'; button.textContent = '查看';
        button.onclick = function() {
            if (dispatchBusy || dispatchPending) return;
            if (dispatchDirty) { shippingError('请先保存当前输入，再切换批次。'); return; }
            selectShippingBatch(batch, false);
        };
        row.append(title, info, status, button); history.appendChild(row);
    });
}
function selectShippingBatch(batch, adding) {
    dispatchBatch = batch;
    document.querySelectorAll('.dispatch-batch-row').forEach(function(row) { row.classList.toggle('is-selected', !!batch && row.dataset.batchId === String(batch.id)); });
    dispatchBatchId = batch ? batch.id : null;
    dispatchNewBatch = adding || !batch;
    var readOnly = batch && batch.status !== 'draft';
    dispatchEditing = !readOnly && !dispatchShipping.shipping_paused;
    setShippingImage(null);
    document.getElementById('shippingModalError').classList.add('d-none');
    document.getElementById('shippingModalTitle').textContent = '第 ' + (batch ? batch.batch_no : dispatchShipping.next_batch_no) + ' 批 · ' + (readOnly ? '发货记录' : '登记发货');
    document.getElementById('shippingDate').value = batch ? batch.shipping_date : localToday();
    document.getElementById('shippingTrackingNo').value = batch ? batch.tracking_no : '';
    document.getElementById('shippingRecordNote').value = batch ? batch.note : '';
    document.getElementById('shippingFields').disabled = !dispatchEditing;
    document.getElementById('shippingFinalRow').classList.toggle('d-none', !!readOnly || dispatchShipping.shipping_paused);
    document.getElementById('shippingFinalBatch').checked = batch ? batch.is_final : !dispatchShipping.shipped_batch_count;
    if (batch && batch.attachment_url) {
        document.getElementById('shippingImagePreview').src = batch.attachment_url;
        document.getElementById('shippingImagePreview').classList.remove('d-none');
    }
    var revertButton = document.getElementById('shippingRevertBtn');
    if (revertButton) revertButton.classList.toggle('d-none', !(batch && batch.id && batch.status !== 'cancelled' && canRevertShipping && !dispatchShipping.shipping_paused));
    document.getElementById('shippingEditBtn').classList.toggle('d-none', !(batch && batch.status === 'shipped') || dispatchShipping.shipping_paused);
    document.getElementById('shippingRecordMeta').textContent = batch && batch.status === 'cancelled' ? '本批已撤销，原记录和图片保留。'
        : (batch && batch.recorded_at ? '登记人：' + batch.recorded_by + ' · 登记时间：' + batch.recorded_at + '（北京时间）'
        : (dispatchShipping.unavailable_reason || '保存信息可暂存本批；登记后保留独立的发货记录。'));
    updateDispatchButtons();
}
function addShippingBatch() {
    if (!dispatchShipping || dispatchBusy || dispatchPending || dispatchShipping.shipping_paused) return;
    if (dispatchDirty) { shippingError('请先保存当前输入，再新增发货批次。'); return; }
    var draft = dispatchShipping.batches.find(function(b) { return b.status === 'draft'; });
    if (draft) {
        selectShippingBatch(draft, false);
        document.getElementById('dispatchSaveMessage').textContent = '请先完成当前草稿批次，再新增下一批。';
        return;
    }
    selectShippingBatch(null, true);
    document.getElementById('dispatchSaveMessage').textContent = '正在新增发货批次；最后一批请勾选整单发货完成。';
    document.getElementById('shippingDate').focus();
}
function openShippingRecord(piId, piNumber) {
    setShippingImage(null);
    currentShippingPiId = piId;
    document.getElementById('shippingPINumber').textContent = piNumber;
    document.getElementById('shippingDate').value = '';
    document.getElementById('shippingTrackingNo').value = '';
    document.getElementById('shippingRecordNote').value = '';
    document.getElementById('shippingFields').disabled = true;
    document.getElementById('shippingSaveBtn').disabled = true;
    var revertButton = document.getElementById('shippingRevertBtn');
    if (revertButton) revertButton.classList.add('d-none');
    document.getElementById('shippingRecordMeta').textContent = '正在读取记录……';
    document.getElementById('shippingModalError').classList.add('d-none');
    return fetch('/api/pi/' + piId + '/shipping-record', {cache:'no-store'})
        .then(function(response) {
            return response.json().then(function(data) { return {ok: response.ok, data: data}; });
        })
        .then(function(result) {
            if (currentShippingPiId !== piId) return;
            if (!result.ok || !result.data.success) throw new Error(result.data.error || '读取发货记录失败。');
            renderShippingRecord(result.data);
        })
        .catch(function(error) { shippingError(error.message || '读取发货记录失败。'); });
}
async function revertShippingRecord() {
    if (!currentShippingPiId || !dispatchBatchId || dispatchBusy || dispatchPending) return;
    if (dispatchDirty) { shippingError('请先保存当前输入，再撤销批次。'); return; }
    if (!confirm('确认撤销第 ' + dispatchBatch.batch_no + ' 批发货登记？本批原记录和图片仍会保留，其他批次不受影响。撤销最后一批后整单恢复未发完状态。')) return;
    dispatchBusy = true; dispatchLock(true); updateDispatchButtons();
    try {
        var response = await fetch('/api/pi/' + currentShippingPiId + '/shipping-batches/' + dispatchBatchId + '/cancel', {
            method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({version:dispatchVersion})
        });
        var data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || '撤销失败，请刷新核对。');
        dispatchChanged = true;
        renderShippingRecord(data, dispatchBatchId);
        document.getElementById('dispatchSaveMessage').textContent = '本批已撤销，其他批次和归档图片保留。';
    } catch (error) { shippingError(error.message); }
    finally { dispatchBusy = false; dispatchLock(false); updateDispatchButtons(); }
}
function customsError(message) {
    var box = document.getElementById('customsModalError');
    box.textContent = message;
    box.classList.remove('d-none');
}
function showDispatchTab(name) {
    bootstrap.Tab.getOrCreateInstance(document.getElementById('dispatch' + name + 'Tab')).show();
}
function resetDispatchScroll() {
    if (dispatchPage) {
        // The full page scrolls with the document; the dialog scrolls internally.
        window.scrollTo(0, window.scrollY + dispatchModal.getBoundingClientRect().top);
    } else {
        dispatchModal.querySelector('.modal-body').scrollTop = 0;
    }
}
function openCustomsRecord(piId, piNumber) {
    dispatchLock(false);
    dispatchDirty = false;
    dispatchBusy = false;
    dispatchPending = null;
    dispatchShipping = null;
    dispatchBatchId = null; dispatchBatch = null; dispatchNewBatch = false;
    document.getElementById('shippingBatchHistory').replaceChildren();
    dispatchVersion = null;
    showDispatchTab('Forwarder');
    updateDispatchButtons();
    document.getElementById('extraExpenseRows').replaceChildren();
    document.getElementById('dispatchSaveMessage').textContent = '保存信息不会改变发货状态';
    document.getElementById('dispatchInfoBtn').disabled = true;
    currentCustomsPiId = piId;
    document.getElementById('customsAttachments').value = '';
    document.getElementById('customsAttachmentList').replaceChildren();
    document.getElementById('customsFolderLink').classList.add('d-none');
    document.getElementById('customsAttachmentStatus').textContent = '正在读取附件…';
    var reads = [loadCustomsAttachments(piId), openShippingRecord(piId, piNumber), openExpense(piId, piNumber)];
    document.getElementById('customsPINumber').textContent = piNumber;
    document.getElementById('customsRequiredYes').checked = false;
    document.getElementById('customsRequiredNo').checked = false;
    document.getElementById('customsNote').value = '';
    document.getElementById('customsForwarder').value = '';
    document.querySelectorAll('#customsForwarder option[data-historical]').forEach(option => option.remove());
    document.getElementById('customsFields').disabled = true;
    document.getElementById('customsDocumentsBtn').classList.add('d-none');
    document.getElementById('customsDocumentsBtn').href = '/pi/' + piId + '/customs-documents';
    document.getElementById('customsRecordMeta').textContent = '正在读取记录……';
    document.getElementById('customsModalError').classList.add('d-none');
    var fullLink = document.getElementById('dispatchFullPageLink');
    if (fullLink) fullLink.href = '/pi/' + piId + '/dispatch?return_to=' + encodeURIComponent(location.pathname + location.search);
    if (!dispatchPage) bootstrap.Modal.getOrCreateInstance(dispatchModal).show();
    reads.push(fetch('/api/pi/' + piId + '/customs-declaration', {cache:'no-store'})
        .then(function(response) {
            return response.json().then(function(data) { return {ok: response.ok, data: data}; });
        })
        .then(function(result) {
            if (currentCustomsPiId !== piId) return;
            if (!result.ok || !result.data.success) throw new Error(result.data.error || '读取报关记录失败。');
            document.getElementById('customsRequiredYes').checked = result.data.customs_required === true;
            document.getElementById('customsRequiredNo').checked = result.data.customs_required === false;
            document.getElementById('customsNote').value = result.data.note || '';
            var forwarderSelect = document.getElementById('customsForwarder');
            var forwarder = result.data.freight_forwarder || '';
            if (forwarder && !Array.from(forwarderSelect.options).some(option => option.value === forwarder)) {
                var option = new Option(forwarder + '（历史选项）', forwarder);
                option.dataset.historical = '1';
                forwarderSelect.add(option);
            }
            forwarderSelect.value = forwarder;
            document.getElementById('customsDocumentsBtn').classList.toggle(
                'd-none', result.data.customs_required !== true
            );
            document.getElementById('customsRecordMeta').textContent = result.data.recorded_at
                ? '最近登记：' + (result.data.recorded_by || '未知用户') + ' · ' + result.data.recorded_at
                : '尚未登记。';
            document.getElementById('customsFields').disabled = false;
            updateDispatchButtons();
        })
        .catch(function(error) { customsError(error.message || '读取报关记录失败。'); }));
    return Promise.all(reads);
}
function clearExpenseAttachment() {
    var input = document.getElementById('exp_attachment');
    if (input) input.value = '';
    if (expenseAttachmentPreviewUrl) URL.revokeObjectURL(expenseAttachmentPreviewUrl);
    expenseAttachmentPreviewUrl = '';
    document.getElementById('exp_attachment_preview').removeAttribute('src');
    document.getElementById('exp_attachment_preview_wrap').classList.add('d-none');
}
function previewExpenseAttachment(input) {
    if (!input.files || !input.files[0]) { clearExpenseAttachment(); return; }
    var file = input.files[0];
    if (!['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(file.type)) {
        clearExpenseAttachment();
        expenseError('附件必须是 JPG、PNG、WebP 或 GIF 图片。');
        return;
    }
    if (file.size > 12 * 1024 * 1024) {
        clearExpenseAttachment();
        expenseError('凭证图片不能超过 12 MB。');
        return;
    }
    if (expenseAttachmentPreviewUrl) URL.revokeObjectURL(expenseAttachmentPreviewUrl);
    expenseAttachmentPreviewUrl = URL.createObjectURL(file);
    document.getElementById('exp_attachment_preview').src = expenseAttachmentPreviewUrl;
    document.getElementById('exp_attachment_preview_wrap').classList.remove('d-none');
    document.getElementById('expenseModalError').classList.add('d-none');
}
function openExpense(piId, piNumber) {
    currentExpensePiId = piId;
    currentExpensePiNumber = piNumber;
    document.getElementById('expensePINumber').textContent = piNumber;
    document.getElementById('exp_category').value = '';
    document.getElementById('exp_amount').value = '';
    document.getElementById('exp_note').value = '';
    clearExpenseAttachment();
    document.getElementById('expenseModalError').classList.add('d-none');
    document.getElementById('expenseModalSuccess').classList.add('d-none');
    return loadExpenseHistory(piId);
}
function loadExpenseHistory(piId) {
    var history = document.getElementById('expenseHistory');
    var summary = document.getElementById('expenseHistorySummary');
    history.className = 'border rounded p-3 text-center text-muted';
    history.replaceChildren();
    var spinner = document.createElement('span');
    spinner.className = 'spinner-border spinner-border-sm me-1';
    history.appendChild(spinner);
    history.appendChild(document.createTextNode('正在读取记录……'));
    summary.textContent = '';
    return fetch('/api/expenses?pi_id=' + encodeURIComponent(piId), {cache: 'no-store'})
        .then(function(response) {
            if (!response.ok) throw new Error('读取真实成本记录失败。');
            return response.json();
        })
        .then(function(records) {
            if (currentExpensePiId !== piId) return;
            var hasOtherExpenses = records.some(function(record) { return !record.is_no_expense_confirmation; });
            if (dispatchShipping) {
                dispatchShipping.expense_count = records.length;
                dispatchShipping.no_expenses_confirmed = records.length > 0 && !hasOtherExpenses;
                updateDispatchButtons();
            }
            history.replaceChildren();
            if (!records.length) {
                history.className = 'border rounded p-3 text-center text-muted';
                history.textContent = '尚未登记真实成本。';
                summary.textContent = '共 0 笔';
                return;
            }
            var rmbTotal = 0;
            var usdTotal = 0;
            records.forEach(function(record) {
                if (record.currency === 'USD') usdTotal += Number(record.amount || 0);
                else rmbTotal += Number(record.amount || 0);
            });
            summary.textContent = '共 ' + records.length + ' 笔 · ¥' + rmbTotal.toFixed(2) +
                (usdTotal ? ' + $' + usdTotal.toFixed(2) : '');
            history.className = 'table-responsive border rounded';
            var table = document.createElement('table');
            table.className = 'table table-sm align-middle mb-0';
            var header = table.createTHead().insertRow();
            ['类别', '备注', '金额', '日期', '凭证', '操作'].forEach(function(label) {
                var th = document.createElement('th');
                th.textContent = label;
                header.appendChild(th);
            });
            var body = table.createTBody();
            records.forEach(function(record) {
                var row = body.insertRow();
                var note = record.note || '-';
                if (record.is_no_expense_confirmation && hasOtherExpenses) note += '（历史确认，后续已登记费用）';
                [record.category || '-', note,
                 (record.currency === 'USD' ? '$' : '¥') + Number(record.amount || 0).toFixed(2),
                 record.created_at || '-'].forEach(function(value) {
                    var cell = row.insertCell();
                    cell.textContent = value;
                });
                var attachmentCell = row.insertCell();
                if (record.has_attachment) {
                    var link = document.createElement('a');
                    link.href = '/expenses/' + record.id + '/attachment';
                    link.target = '_blank';
                    link.rel = 'noopener';
                    link.className = 'btn btn-sm btn-outline-primary';
                    link.textContent = '查看图片';
                    attachmentCell.appendChild(link);
                } else {
                    attachmentCell.textContent = '—';
                }
                var actionCell = row.insertCell();
                Array.from(row.cells).forEach(function(cell, index) { cell.dataset.label = ['类别', '备注', '金额', '日期', '凭证', '操作'][index]; });
                if (canDeleteExpense) {
                    var remove = document.createElement('button');
                    remove.type = 'button';
                    remove.className = 'btn btn-sm btn-outline-danger';
                    remove.textContent = '删除';
                    remove.onclick = function() { deleteExpenseFromPIList(record.id); };
                    actionCell.appendChild(remove);
                } else {
                    actionCell.textContent = '—';
                }
            });
            history.appendChild(table);
        })
        .catch(function(error) {
            history.className = 'alert alert-danger mb-0';
            history.textContent = error.message || '读取真实成本记录失败。';
        });
}
function deleteExpenseFromPIList(expenseId) {
    if (dispatchBusy || dispatchPending) return;
    if (!confirm('确定删除这条真实成本记录吗？')) return;
    fetch('/api/expenses/' + expenseId, {method: 'DELETE'})
        .then(function(response) {
            return response.json().then(function(data) { return {ok: response.ok, data: data}; });
        })
        .then(function(result) {
            if (!result.ok || !result.data.success) throw new Error(result.data.error || '删除失败。');
            document.getElementById('expenseModalSuccess').textContent = '真实成本记录已删除。';
            document.getElementById('expenseModalSuccess').classList.remove('d-none');
            dispatchChanged = true;
            if (result.data.dispatch && dispatchShipping) {
                Object.assign(dispatchShipping, result.data.dispatch);
                dispatchVersion = result.data.dispatch.version;
            }
            loadExpenseHistory(currentExpensePiId);
        })
        .catch(function(error) { expenseError(error.message || '删除失败。'); });
}
function expenseError(message) {
    var box = document.getElementById('expenseModalError');
    box.textContent = message;
    box.classList.remove('d-none');
}
function renderCustomsAttachments(data, piId) {
 if (currentCustomsPiId !== piId) return;
 var list=document.getElementById('customsAttachmentList');list.replaceChildren();
 data.files.forEach(function(file){var row=document.createElement('div');row.className='d-flex gap-2 align-items-center mb-1';var link=document.createElement('a');link.href=file.url;link.target='_blank';link.textContent=file.name;link.className='text-break';var size=document.createElement('small');size.className='text-muted';size.textContent=file.size;var download=document.createElement('a');download.href=file.download_url;download.textContent='下载';download.className='small text-nowrap';row.append(link,size,download);list.appendChild(row);});
 var folder=document.getElementById('customsFolderLink');folder.href=data.folder_url;folder.classList.remove('d-none');
 document.getElementById('customsAttachmentStatus').textContent=data.files.length?'已归档 '+data.files.length+' 个附件':'暂无附件';
}
async function loadCustomsAttachments(piId) {
 try {var response=await fetch('/api/pi/'+piId+'/customs-attachments');var data=await response.json();if(!response.ok)throw Error(data.error||'读取附件失败');renderCustomsAttachments(data,piId);}
 catch(error){if(currentCustomsPiId===piId)document.getElementById('customsAttachmentStatus').textContent=error.message;}
}
async function uploadCustomsAttachments() {
 var piId=currentCustomsPiId,input=document.getElementById('customsAttachments'),button=document.getElementById('customsUploadBtn'),status=document.getElementById('customsAttachmentStatus');
 var files=Array.from(input.files||[]);if(!files.length||files.length>8){status.textContent='请选择1至8个文件';return;}
 if(files.some(f=>f.size>20*1024*1024)||files.reduce((s,f)=>s+f.size,0)>30*1024*1024){status.textContent='单个文件最大20MB，每批合计最大30MB';return;}
 var form=new FormData();files.forEach(f=>form.append('files',f));dispatchUploading=true;button.disabled=true;status.textContent='正在上传…';
 try {var response=await fetch('/api/pi/'+piId+'/customs-attachments',{method:'POST',body:form});var data=await response.json();if(!response.ok)throw Error(data.error||'上传失败');if(currentCustomsPiId===piId){input.value='';renderCustomsAttachments(data,piId);}}
 catch(error){if(currentCustomsPiId===piId)status.textContent=error.message||'上传失败，请重试';}
 finally {dispatchUploading=false;button.disabled=false;}
}

// Keep the fast dialog entry; transfer only saved data to the complete page.
var dispatchFullPageLink = document.getElementById('dispatchFullPageLink');
if (dispatchFullPageLink) dispatchFullPageLink.addEventListener('click', function(event) {
    if (dispatchBusy || dispatchPending || dispatchUploading || dispatchDirty) {
        event.preventDefault();
        document.getElementById('dispatchSaveMessage').textContent = '请先保存当前输入，待上传完成后再打开完整页面。';
        return;
    }
    var target = new URL(this.href);
    var tab = dispatchModal.querySelector('[role="tab"].active');
    target.searchParams.set('tab', tab.id.replace('dispatch', '').replace('Tab', '').toLowerCase());
    this.href = target.href;
    try { sessionStorage.setItem('dispatch-return-' + currentCustomsPiId, JSON.stringify({query: dispatchQueryKey(location.search), y: scrollY})); } catch (_) {}
});
function dispatchQueryKey(search) {
    var params = new URLSearchParams(search);
    if (!Array.from(params).length) params.set('stage', '');
    params.sort(); return params.toString();
}
if (dispatchPage) {
    var initialTab = new URLSearchParams(location.search).get('tab');
    openCustomsRecord(Number(dispatchModal.dataset.piId), dispatchModal.dataset.piNumber).then(function() {
        if (dispatchShipping && !document.getElementById('customsFields').disabled) {
            var names = {forwarder:'Forwarder', expenses:'Expenses', shipping:'Shipping'};
            showDispatchTab(names[initialTab] || 'Forwarder');
        } else {
            document.getElementById('dispatchPageStatus').textContent = '读取失败';
            document.getElementById('dispatchSaveMessage').textContent = '记录未能完整读取，请刷新页面后重试。';
        }
    });
} else {
    var returningPI = location.hash.match(/^#pi-row-(\d+)$/);
    if (returningPI) {
        try {
            var key = 'dispatch-return-' + returningPI[1];
            var savedPosition = JSON.parse(sessionStorage.getItem(key) || 'null');
            sessionStorage.removeItem(key);
            if (savedPosition && savedPosition.query === dispatchQueryKey(location.search)) {
                window.addEventListener('load', function() { requestAnimationFrame(function() { window.scrollTo(0, savedPosition.y); }); }, {once:true});
            }
        } catch (_) {}
    }
}
