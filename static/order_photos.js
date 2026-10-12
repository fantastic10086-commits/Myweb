'use strict';
(() => {
  const get = id => document.getElementById(id);
  const modal = get('orderPhotosModal');
  if (!modal) return;
  let orderId, photos = [], page = 0, total = 0, more = false, index = -1;
  let controller, generation = 0, busy = false;
  const fileUrl = (photo, query = '') => '/api/mobile/photos/' + photo.id + '/file' + query;
  const status = text => { get('orderPhotosStatus').textContent = text; };
  function controls() {
    get('orderPhotosMore').hidden = index >= 0 || !more;
    get('orderPhotosMore').disabled = busy;
    get('orderPhotoPrevious').disabled = busy || index <= 0;
    get('orderPhotoNext').disabled = busy || (index >= photos.length - 1 && !more);
  }
  function showPhoto(next) {
    if (!photos[next]) return;
    index = next;
    get('orderPhotosGrid').hidden = true;
    get('orderPhotoPreview').hidden = false;
    const photo = photos[index], image = get('orderPhotoOriginal');
    status('');
    image.alt = photo.name;
    image.src = fileUrl(photo);
    get('orderPhotoCaption').textContent = photo.name + (photo.note ? ' · ' + photo.note : '');
    get('orderPhotoPosition').textContent = (index + 1) + ' / ' + total;
    get('orderPhotoDownload').href = fileUrl(photo, '?download=1');
    controls();
  }
  function addCard(photo, position) {
    const col = document.createElement('div'); col.className = 'col-6 col-md-4 col-lg-3';
    const button = document.createElement('button'); button.type = 'button';
    button.className = 'btn border p-2 w-100 h-100 text-start';
    button.setAttribute('aria-label', '放大查看：' + photo.name);
    const image = document.createElement('img'); image.src = fileUrl(photo, '?thumbnail=1');
    image.alt = photo.name; image.loading = 'lazy'; image.className = 'w-100 rounded';
    image.style.cssText = 'height:160px;object-fit:contain;background:#f5f6f8';
    const label = document.createElement('span'); label.className = 'd-block small text-break mt-2';
    label.textContent = photo.note || photo.name;
    image.onerror = () => { label.textContent = '缩略图加载失败，点击查看原图'; };
    button.append(image, label); button.addEventListener('click', () => showPhoto(position));
    col.append(button); get('orderPhotosGrid').append(col);
  }
  async function loadPage() {
    if (busy) return false;
    const current = generation;
    busy = true; controls(); status('正在加载照片…'); get('orderPhotosRetry').hidden = true;
    const requestController = new AbortController(); controller = requestController;
    const timeout = setTimeout(() => requestController.abort(), 20000);
    try {
      const response = await fetch('/api/mobile/orders/' + orderId + '/photos?page=' + (page + 1), {
        credentials: 'same-origin', cache: 'no-store', signal: requestController.signal, redirect: 'error'
      });
      const data = await response.json();
      if (current !== generation) return false;
      if (!response.ok) throw new Error(data.error || '照片加载失败，请重试。');
      page++; total = data.total; more = data.has_more;
      get('orderPhotosTitle').textContent = data.order.number + ' · 归档照片';
      get('orderPhotosSummary').textContent = data.order.customer_name + (data.order.customer_country ? '（' + data.order.customer_country + '）' : '') + ' · 共 ' + total + ' 张';
      for (const photo of data.photos) { addCard(photo, photos.length); photos.push(photo); }
      status(total ? '' : '该订单暂无归档照片。');
      return true;
    } catch (error) {
      if (current === generation) {
        status(error.name === 'AbortError' ? '加载超时，请重试。' : (error.message || '加载失败，请重试。'));
        get('orderPhotosRetry').hidden = false;
      }
      return false;
    } finally {
      clearTimeout(timeout);
      if (current === generation) { busy = false; controls(); }
    }
  }
  function reset() {
    generation++; if (controller) controller.abort();
    photos = []; page = total = 0; more = busy = false; index = -1;
    get('orderPhotosGrid').replaceChildren(); get('orderPhotosGrid').hidden = false;
    get('orderPhotoOriginal').removeAttribute('src'); get('orderPhotoDownload').removeAttribute('href');
    get('orderPhotoPreview').hidden = true; get('orderPhotosRetry').hidden = true;
    get('orderPhotosSummary').textContent = ''; get('orderPhotosTitle').textContent = '订单归档照片';
    status(''); controls();
  }
  document.querySelectorAll('[data-order-photos]').forEach(button => button.addEventListener('click', () => {
    reset(); orderId = button.dataset.orderPhotos;
    bootstrap.Modal.getOrCreateInstance(modal).show(); loadPage();
  }));
  modal.addEventListener('hidden.bs.modal', reset);
  get('orderPhotosMore').addEventListener('click', loadPage);
  get('orderPhotosRetry').addEventListener('click', loadPage);
  get('orderPhotosBack').addEventListener('click', () => {
    index = -1; get('orderPhotoPreview').hidden = true; get('orderPhotosGrid').hidden = false;
    get('orderPhotoOriginal').removeAttribute('src'); status(''); controls();
  });
  get('orderPhotoOriginal').addEventListener('error', () => { if (index >= 0) status('原图加载失败，可尝试下载或重新打开照片。'); });
  get('orderPhotoPrevious').addEventListener('click', () => showPhoto(index - 1));
  get('orderPhotoNext').addEventListener('click', async () => {
    const current = generation, next = index + 1;
    if (next >= photos.length && more && !await loadPage()) return;
    if (current === generation) showPhoto(next);
  });
  modal.addEventListener('keydown', event => {
    if (index < 0 || busy || event.target.tagName === 'A') return;
    if (event.key === 'ArrowLeft') { event.preventDefault(); get('orderPhotoPrevious').click(); }
    if (event.key === 'ArrowRight') { event.preventDefault(); get('orderPhotoNext').click(); }
  });
})();
