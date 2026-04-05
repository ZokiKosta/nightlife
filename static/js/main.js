/* NOCTURN — main.js */

// Mobile nav toggle
const hamburger = document.getElementById('navHamburger');
const mobileMenu = document.getElementById('mobileMenu');
if (hamburger && mobileMenu) {
    hamburger.addEventListener('click', () => mobileMenu.classList.toggle('open'));
    document.addEventListener('click', (e) => {
        if (!hamburger.contains(e.target) && !mobileMenu.contains(e.target))
            mobileMenu.classList.remove('open');
    });
}

// Stagger animate cards on page load
document.addEventListener('DOMContentLoaded', () => {
    const cards = document.querySelectorAll(
        '.event-card, .feature-card, .step-card, .event-preview-card'
    );
    cards.forEach((card, i) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
        setTimeout(() => {
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 60 + i * 60);
    });

    // Proxy Instagram CDN images through Flask to avoid expired-URL failures
    proxyInstagramImages();
});

/**
 * For every <img> whose src contains a known Instagram CDN domain,
 * rewrite it to go through /events/image-proxy?url=...
 * This avoids broken images when CDN tokens expire.
 */
function proxyInstagramImages() {
    const CDN_MARKERS = ['cdninstagram.com', 'fbcdn.net', 'scontent'];
    document.querySelectorAll('img[data-src], img[src]').forEach(img => {
        const src = img.dataset.src || img.src || '';
        if (CDN_MARKERS.some(m => src.includes(m))) {
            const proxied = '/events/image-proxy?url=' + encodeURIComponent(src);
            if (img.dataset.src) {
                img.dataset.src = proxied;
            } else {
                img.src = proxied;
            }
        }
    });
}

// Also rewrite CSS background-image inline styles (used in .epc-img)
document.addEventListener('DOMContentLoaded', () => {
    const CDN_MARKERS = ['cdninstagram.com', 'fbcdn.net', 'scontent'];
    document.querySelectorAll('[style*="background-image"]').forEach(el => {
        const style = el.getAttribute('style') || '';
        const match = style.match(/url\(['"]?([^'")\s]+)['"]?\)/);
        if (match && CDN_MARKERS.some(m => match[1].includes(m))) {
            const proxied = '/events/image-proxy?url=' + encodeURIComponent(match[1]);
            el.style.backgroundImage = `url('${proxied}')`;
        }
    });
});

// Auto-dismiss flash messages
document.querySelectorAll('.flash').forEach(el => {
    setTimeout(() => {
        el.style.transition = 'opacity 0.5s';
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 500);
    }, 4000);
});