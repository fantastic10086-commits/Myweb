(function () {
    'use strict';
    const types = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif'};
    window.PIItemImages = {
        markup: function (id) {
            return '<div class="pi-item-image border rounded p-1 text-center" tabindex="0" title="点击上传，或在此处 Ctrl+V / ⌘V 粘贴图片" style="width:78px;flex-shrink:0;">' +
                '<img class="pi-item-image-preview" alt="产品图片" style="width:64px;height:56px;object-fit:contain;display:none;">' +
                '<span class="pi-item-image-empty text-muted small">无图片</span>' +
                '<button type="button" class="btn btn-link btn-sm p-0 d-block w-100 pi-image-pick pi-structural-control">上传/更换</button>' +
                '<button type="button" class="btn btn-link btn-sm p-0 pi-image-reset pi-structural-control" title="恢复产品库图片">恢复</button> ' +
                '<button type="button" class="btn btn-link btn-sm p-0 text-danger pi-image-clear pi-structural-control">移除</button>' +
                '<input type="file" class="d-none pi-image-file pi-structural-control" accept="image/jpeg,image/png,image/webp,image/gif" name="item_image_file_' + id + '">' +
                '<input type="hidden" class="pi-image-mode" name="item_image_mode_' + id + '">' +
                '<input type="hidden" class="pi-image-source" name="item_image_source_' + id + '"></div>';
        },
        mount: function (row, id, state, p) {
            const area = row.querySelector('.pi-item-image');
            const input = area.querySelector('.pi-image-file');
            const preview = area.querySelector('.pi-item-image-preview');
            const empty = area.querySelector('.pi-item-image-empty');
            state.originalImage = p.originalImage || '';
            state.imageSource = p.imageSource || '';
            state.imageMode = p.imageMode || 'keep';
            state.imageFile = p.imageFile || null;
            let objectUrl = null;
            function assignFile() {
                if (!state.imageFile) { input.value = ''; return; }
                const transfer = new DataTransfer();
                transfer.items.add(state.imageFile);
                input.files = transfer.files;
            }
            function render() {
                if (objectUrl) URL.revokeObjectURL(objectUrl);
                objectUrl = state.imageFile ? URL.createObjectURL(state.imageFile) : null;
                const image = state.imageMode === 'clear' ? '' : (state.imageMode === 'catalog' ? state.originalImage : state.img);
                const src = objectUrl || (image ? '/uploads/thumb/' + encodeURIComponent(image) : '');
                preview.style.display = src ? '' : 'none';
                empty.style.display = src ? 'none' : '';
                if (src) preview.src = src; else preview.removeAttribute('src');
                area.querySelector('.pi-image-mode').value = state.imageMode;
                area.querySelector('.pi-image-source').value = state.imageSource;
            }
            function selectFile(file) {
                if (!file || input.disabled) return;
                if (!types[file.type] || file.size > 12 * 1024 * 1024) {
                    alert('仅支持 JPG、PNG、WebP、GIF 图片，单张最大 12 MB。');
                    assignFile();
                    return;
                }
                state.imageFile = file;
                state.imageMode = 'keep';
                assignFile();
                render();
            }
            area.querySelector('.pi-image-pick').addEventListener('click', function () { input.click(); });
            input.addEventListener('change', function () { selectFile(input.files[0]); });
            area.addEventListener('paste', function (event) {
                if (input.disabled) return;
                const items = event.clipboardData && event.clipboardData.items;
                if (!items) return;
                for (const item of items) {
                    if (item.type.indexOf('image/') !== 0) continue;
                    const blob = item.getAsFile();
                    if (!blob) continue;
                    event.preventDefault();
                    event.stopPropagation();
                    selectFile(new File([blob], 'pi-product-' + Date.now() + '.' + (types[blob.type] || 'png'), {type: blob.type}));
                    return;
                }
            });
            function reset(mode) {
                if (input.disabled) return;
                state.imageFile = null;
                state.imageSource = '';
                state.imageMode = mode;
                state.img = mode === 'catalog' ? state.originalImage : '';
                assignFile();
                render();
            }
            area.querySelector('.pi-image-reset').addEventListener('click', function () { reset('catalog'); });
            area.querySelector('.pi-image-clear').addEventListener('click', function () { reset('clear'); });
            assignFile();
            render();
        }
    };
})();
