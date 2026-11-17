(() => {
  const articles = [...document.querySelectorAll('.milestone')];
  const panels = [...document.querySelectorAll('.stage-panel')];
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  const links = [...document.querySelectorAll('.milestone-link')];
  function show() {
    const selected = document.getElementById(location.hash.slice(1));
    const panel = selected?.classList.contains('stage-panel') ? selected : panels[0];
    const article = panel.closest('.milestone');
    articles.forEach(item => item.hidden = item !== article);
    panels.forEach(item => item.hidden = item !== panel);
    tabs.forEach(item => {
      const active = item.getAttribute('aria-controls') === panel.id;
      item.setAttribute('aria-selected', String(active));
      item.tabIndex = active ? 0 : -1;
    });
    links.forEach(item => {
      const active = item.dataset.milestone === article.id;
      item.classList.toggle('active', active);
      if (active) item.setAttribute('aria-current', 'step'); else item.removeAttribute('aria-current');
    });
  }
  window.addEventListener('hashchange', show);
  show();
  tabs.forEach((tab) => tab.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const siblings = [...tab.parentElement.querySelectorAll('[role="tab"]')];
    let next = event.key === 'Home' ? 0 : event.key === 'End' ? siblings.length - 1 : (siblings.indexOf(tab) + (event.key === 'ArrowRight' ? 1 : -1) + siblings.length) % siblings.length;
    siblings[next].click(); siblings[next].focus();
  }));
  const dialog = document.getElementById('image-viewer');
  const image = document.getElementById('viewer-image');
  const scroll = document.querySelector('.viewer-scroll');
  function fit() { image.style.width = Math.max(200, scroll.clientWidth - 40) + 'px'; }
  document.querySelectorAll('[data-figure]').forEach(button => button.addEventListener('click', () => {
    image.src = button.dataset.figure;
    image.alt = button.dataset.caption;
    document.getElementById('viewer-caption').textContent = image.alt;
    document.getElementById('viewer-kind').textContent = image.alt.includes('Working application') ? 'Working application screenshot' : 'Explanatory proposal diagram';
    dialog.showModal(); fit(); scroll.scrollTo(0, 0);
  }));
  document.getElementById('fit-image').addEventListener('click', fit);
  document.getElementById('actual-image').addEventListener('click', () => image.style.width = image.naturalWidth + 'px');
  document.getElementById('close-image').addEventListener('click', () => dialog.close());
  document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
    const text = document.getElementById(button.dataset.copy).textContent;
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = 'Copied';
    } catch {
      const range = document.createRange(); range.selectNodeContents(document.getElementById(button.dataset.copy));
      const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      button.textContent = 'Selected — copy with your keyboard';
    }
  }));
})();
