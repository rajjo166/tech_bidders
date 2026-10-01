document.addEventListener("DOMContentLoaded", () => {
    const dateInput = document.querySelector("#booking_date");
    if (dateInput) {
        const today = new Date().toISOString().split("T")[0];
        dateInput.min = today;
    }

    setTimeout(() => {
        document.querySelectorAll(".alert").forEach(el => {
            try {
                bootstrap.Alert.getOrCreateInstance(el).close();
            } catch (e) {}
        });
    }, 5000);
});
