// Detect if embedded via URL parameter or iframe
const isEmbedded =
  new URLSearchParams(window.location.search).get('embed') === 'true' ||
  window.self !== window.top;

if (isEmbedded) {
  // Add class to hide header/footer via CSS
  document.documentElement.classList.add('embedded');

  // Communicate height to parent for responsive iframe
  const observer = new ResizeObserver(([entry]) => {
    parent.postMessage({height: entry.target.offsetHeight}, "*");
  });
  observer.observe(document.documentElement);
}

export {isEmbedded};
