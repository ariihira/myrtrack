document.addEventListener('DOMContentLoaded', function() {
    const grid = document.querySelector('.directory-list');
    const containers = document.querySelectorAll('.group-container');

    const updateSpan = (container) => {
        const content = container.querySelector('.group-dropdown');
        
        // 1. Reset span to auto to get the natural height of the content
        container.style.gridRowEnd = 'auto';
        
        // 2. Measure the height in pixels
        const height = content.offsetHeight;
        
        // 3. Set the span equal to the height + desired vertical gap (e.g., 20px)
        const verticalGap = 20;
        container.style.gridRowEnd = `span ${height + verticalGap}`;
    };

    // Initial layout calculation
    containers.forEach(container => updateSpan(container));

    // Update when a card is toggled
    grid.addEventListener('toggle', (e) => {
        if (e.target.tagName === 'DETAILS') {
            updateSpan(e.target.closest('.group-container'));
        }
    }, true);

    // Recalculate on window resize
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            containers.forEach(container => updateSpan(container));
        }, 100);
    });
});