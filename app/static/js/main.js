/**
 * RailSathi PK - Main Client Scripts
 */
document.addEventListener("DOMContentLoaded", () => {
    // Auto-dismiss standard alerts after 6 seconds
    const alerts = document.querySelectorAll(".alert-dismissible:not(.alert-permanent)");
    alerts.forEach((alertEl) => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alertEl);
            if (bsAlert) {
                bsAlert.close();
            }
        }, 6000);
    });
});

