/* Procurement-only files. Pasted images stay in a visible queue until uploaded. */
(function () {
    'use strict';
    document.addEventListener('DOMContentLoaded', function () {
        var root = document.getElementById('procAttachments');
        if (!root) return;
        var input = document.getElementById('procAttachmentInput');
        var choose = document.getElementById('procAttachmentChoose');
        var upload = document.getElementById('procAttachmentUpload');
        var reload = document.getElementById('procAttachmentReload');
        var status = document.getElementById('procAttachmentStatus');
        var pendingList = document.getElementById('procAttachmentPending');
        var savedList = document.getElementById('procAttachmentList');
        var queue = [], busy = false, savedFiles = [];
        var extensions = /\.(jpg|jpeg|png|webp|gif|pdf|doc|docx|xls|xlsx|ppt|pptx|txt|csv|zip)$/i;

        function message(text, error) {
            status.textContent = text;
            status.classList.toggle('text-danger', !!error);
            status.classList.toggle('text-muted', !error);
        }
        function sizeLabel(size) {
            return size >= 1024 * 1024 ? (size / 1024 / 1024).toFixed(1) + ' MB' : Math.max(1, Math.ceil(size / 1024)) + ' KB';
        }
        function setBusy(value) {
            busy = value;
            input.disabled = value;
            choose.disabled = value;
            reload.disabled = value;
            upload.disabled = value || !queue.length;
            root.querySelectorAll('[data-attachment-action]').forEach(function(button) { button.disabled = value; });
        }
        function card(name, size, imageUrl) {
            var row = document.createElement('div'); row.className = 'proc-attachment-item';
            var picture;
            if (imageUrl) {
                picture = document.createElement('img'); picture.src = imageUrl; picture.alt = name;
                picture.loading = 'lazy'; picture.className = 'proc-attachment-thumb';
            } else {
                picture = document.createElement('span'); picture.className = 'proc-attachment-thumb d-flex justify-content-center align-items-center text-muted fs-3';
                picture.innerHTML = '<i class="bi bi-file-earmark"></i>';
            }
            var details = document.createElement('div'); details.className = 'proc-attachment-details';
            var title = document.createElement('span'); title.className = 'proc-attachment-name small fw-semibold';
            title.textContent = name; title.title = name;
            var info = document.createElement('small'); info.className = 'text-muted'; info.textContent = size;
            var actions = document.createElement('div'); actions.className = 'd-flex flex-wrap gap-2 mt-1';
            details.append(title, info, actions); row.append(picture, details);
            return {row:row, actions:actions, picture:picture};
        }
        function actionButton(label, callback) {
            var button = document.createElement('button'); button.type = 'button';
            button.className = 'btn btn-link btn-sm p-0'; button.textContent = label;
            button.dataset.attachmentAction = '1'; button.disabled = busy;
            button.addEventListener('click', callback); return button;
        }
        function link(label, url, newTab) {
            var a = document.createElement('a'); a.href = url; a.textContent = label; a.className = 'small';
            if (newTab) { a.target = '_blank'; a.rel = 'noopener'; }
            return a;
        }
        function renderQueue() {
            pendingList.replaceChildren();
            pendingList.classList.toggle('d-none', !queue.length);
            queue.forEach(function(item, index) {
                var view = card(item.file.name, '待上传 · ' + sizeLabel(item.file.size), item.preview);
                view.actions.appendChild(actionButton('移除', function() {
                    if (busy) return;
                    if (item.preview) URL.revokeObjectURL(item.preview);
                    queue.splice(index, 1); renderQueue();
                    message(queue.length ? '待上传 ' + queue.length + ' 个附件。' : '已清空待上传附件。');
                }));
                pendingList.appendChild(view.row);
            });
            upload.disabled = busy || !queue.length;
            upload.textContent = queue.length ? '上传附件（' + queue.length + '）' : '上传附件';
        }
        function renderSaved(data) {
            savedFiles = data.files;
            savedList.replaceChildren();
            document.getElementById('procAttachmentCount').textContent = savedFiles.length;
            savedFiles.forEach(function(file) {
                var view = card(file.name, file.size, file.is_image ? file.thumbnail_url : '');
                view.actions.append(link('查看', file.url, true), link('下载', file.download_url));
                if (file.delete_url) view.actions.appendChild(actionButton('删除', function() { removeFile(file); }));
                savedList.appendChild(view.row);
            });
        }
        function addFiles(files) {
            if (busy) { message('附件正在处理，请稍后再添加。', true); return; }
            if (!files.length) return;
            if (queue.length + files.length > 8) { message('每次最多上传 8 个附件，请先上传或移除待上传文件。', true); return; }
            var bad = files.find(function(f) { return !extensions.test(f.name) || !f.size || f.size > 20 * 1024 * 1024; });
            if (bad) { message('“' + bad.name + '”格式不支持、内容为空或超过 20 MB。', true); return; }
            var total = queue.reduce(function(sum, item) { return sum + item.file.size; }, 0) + files.reduce(function(sum, f) { return sum + f.size; }, 0);
            if (total > 30 * 1024 * 1024) { message('每批附件合计不能超过 30 MB，请分批上传。', true); return; }
            files.forEach(function(file) {
                queue.push({file:file, preview:/\.(jpg|jpeg|png|webp|gif)$/i.test(file.name) ? URL.createObjectURL(file) : ''});
            });
            renderQueue(); message('待上传 ' + queue.length + ' 个附件，点击“上传附件”保存。');
        }
        async function request(url, options) {
            var response = await fetch(url, options || {cache:'no-store'});
            var data;
            try { data = await response.json(); }
            catch (_) { throw Error('附件请求未完成，请检查登录状态后刷新附件。'); }
            if (!response.ok) throw Error(data.error || '附件处理失败，请重试。');
            if (!Array.isArray(data.files)) throw Error('附件响应异常，请刷新附件核对。');
            return data;
        }
        async function load() {
            if (busy) return;
            setBusy(true); message('正在读取附件…');
            try {
                renderSaved(await request(root.dataset.url));
                message(queue.length ? '待上传 ' + queue.length + ' 个附件。' : (savedFiles.length ? '已保存 ' + savedFiles.length + ' 个采购附件。' : '暂无采购附件。'));
            } catch (error) { message(error.message, true); }
            finally { setBusy(false); }
        }
        async function removeFile(file) {
            if (busy || !window.confirm('确认删除采购附件“' + file.name + '”？')) return;
            setBusy(true); message('正在删除附件…');
            try { renderSaved(await request(file.delete_url, {method:'POST'})); message('附件已删除。'); }
            catch (error) { message(error.message, true); }
            finally { setBusy(false); }
        }
        upload.addEventListener('click', async function() {
            if (busy || !queue.length) return;
            var form = new FormData(); queue.forEach(function(item) { form.append('files', item.file, item.file.name); });
            setBusy(true); message('正在上传附件…');
            try {
                renderSaved(await request(root.dataset.url, {method:'POST', body:form}));
                queue.forEach(function(item) { if (item.preview) URL.revokeObjectURL(item.preview); });
                queue = []; renderQueue(); message('上传成功，已保存 ' + savedFiles.length + ' 个采购附件。');
            } catch (error) { message(error.message + ' 待上传文件已保留；可先刷新附件核对上传结果。', true); }
            finally { setBusy(false); }
        });
        choose.addEventListener('click', function() { if (!busy) input.click(); });
        input.addEventListener('change', function() { addFiles(Array.from(input.files || [])); input.value = ''; });
        reload.addEventListener('click', load);
        document.addEventListener('paste', function(event) {
            if (event.defaultPrevented || document.querySelector('.modal.show') || !event.clipboardData) return;
            var files = Array.from(event.clipboardData.items || []).filter(function(item) {
                return item.kind === 'file' && item.type.indexOf('image/') === 0;
            }).map(function(item) { return item.getAsFile(); }).filter(Boolean);
            if (!files.length) return;
            event.preventDefault();
            files = files.map(function(file, index) {
                var extension = ({'image/jpeg':'jpg','image/png':'png','image/webp':'webp','image/gif':'gif'})[file.type];
                return extension ? new File([file], '采购图片-' + Date.now() + '-' + (index + 1) + '.' + extension, {type:file.type}) : file;
            });
            addFiles(files);
            if (!busy) document.getElementById('procAttachmentPaste').scrollIntoView({block:'nearest'});
        });
        window.addEventListener('beforeunload', function(event) {
            if (!queue.length) return;
            event.preventDefault(); event.returnValue = '';
        });
        load();
    });
})();
