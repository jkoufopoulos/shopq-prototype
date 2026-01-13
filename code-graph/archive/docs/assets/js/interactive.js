// This file adds interactivity to the analysis documentation, enhancing user experience.

document.addEventListener("DOMContentLoaded", function() {
    // Add event listeners or interactive features here
    console.log("Interactive JavaScript loaded.");

    // Example: Toggle visibility of sections
    const toggleButtons = document.querySelectorAll('.toggle-section');
    toggleButtons.forEach(button => {
        button.addEventListener('click', function() {
            const section = document.querySelector(`#${this.dataset.target}`);
            section.classList.toggle('hidden');
        });
    });

    // Example: Initialize tooltips or popovers
    const tooltips = document.querySelectorAll('[data-tooltip]');
    tooltips.forEach(tooltip => {
        tooltip.addEventListener('mouseenter', function() {
            const tooltipText = this.dataset.tooltip;
            const tooltipElement = document.createElement('div');
            tooltipElement.className = 'tooltip';
            tooltipElement.innerText = tooltipText;
            document.body.appendChild(tooltipElement);
            const rect = this.getBoundingClientRect();
            tooltipElement.style.left = `${rect.left + window.scrollX}px`;
            tooltipElement.style.top = `${rect.bottom + window.scrollY}px`;
        });

        tooltip.addEventListener('mouseleave', function() {
            const tooltipElement = document.querySelector('.tooltip');
            if (tooltipElement) {
                tooltipElement.remove();
            }
        });
    });
});
