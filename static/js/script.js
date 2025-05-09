document.addEventListener('DOMContentLoaded', function () {
    // Get references to the elements
    const hospitalSelect = document.getElementById('hospital');
    const departmentSelect = document.getElementById('department');
    const doctorSelect = document.getElementById('doctor');
    const dateInput = document.getElementById('date');
    const timeSelect = document.getElementById('time');
    const slotAvailabilityDiv = document.getElementById('slotAvailability');
    const submitBtn = document.getElementById('submitBtn');
    const loadingSpinner = document.getElementById('loadingSpinner');

    // Function to reset and disable dependent dropdowns
    function resetDependentDropdowns() {
        departmentSelect.innerHTML = '<option value="" disabled selected>Pick a hospital first</option>';
        departmentSelect.disabled = true;
        doctorSelect.innerHTML = '<option value="" disabled selected>Pick a department first</option>';
        doctorSelect.disabled = true;
        timeSelect.innerHTML = '<option value="" disabled selected>Select a date first</option>';
        timeSelect.disabled = true;
        slotAvailabilityDiv.textContent = '';
        submitBtn.disabled = true;
    }

    // Load departments when a hospital is selected
    function loadDepartments() {
        const hospitalId = hospitalSelect.value;
        resetDependentDropdowns();

        if (hospitalId) {
            departmentSelect.innerHTML = '<option value="" disabled selected>Loading departments...</option>';
            fetch(`/get_departments/${hospitalId}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Network response was not ok');
                    }
                    return response.json();
                })
                .then(data => {
                    departmentSelect.innerHTML = '<option value="" disabled selected>Select a department</option>';
                    if (data.length === 0) {
                        departmentSelect.innerHTML = '<option value="" disabled selected>No departments available</option>';
                    } else {
                        data.forEach(dept => {
                            const option = document.createElement('option');
                            option.value = dept[0];
                            option.textContent = dept[1];
                            departmentSelect.appendChild(option);
                        });
                        departmentSelect.disabled = false;
                    }
                })
                .catch(error => {
                    console.error('Error fetching departments:', error);
                    departmentSelect.innerHTML = '<option value="" disabled selected>Error loading departments</option>';
                });
        }
    }

    // Load doctors when a department is selected
    function loadDoctors() {
        const departmentId = departmentSelect.value;
        doctorSelect.innerHTML = '<option value="" disabled selected>Loading doctors...</option>';
        doctorSelect.disabled = true;
        timeSelect.innerHTML = '<option value="" disabled selected>Select a date first</option>';
        timeSelect.disabled = true;
        slotAvailabilityDiv.textContent = '';
        submitBtn.disabled = true;

        if (departmentId) {
            fetch(`/get_doctors/${departmentId}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Network response was not ok');
                    }
                    return response.json();
                })
                .then(data => {
                    doctorSelect.innerHTML = '<option value="" disabled selected>Select a doctor</option>';
                    if (data.length === 0) {
                        doctorSelect.innerHTML = '<option value="" disabled selected>No doctors available</option>';
                    } else {
                        data.forEach(doc => {
                            const option = document.createElement('option');
                            option.value = doc[0];
                            option.textContent = doc[1];
                            doctorSelect.appendChild(option);
                        });
                        doctorSelect.disabled = false;
                    }
                })
                .catch(error => {
                    console.error('Error fetching doctors:', error);
                    doctorSelect.innerHTML = '<option value="" disabled selected>Error loading doctors</option>';
                });
        }
    }

    // Load available time slots when a doctor and date are selected
    function loadAvailableSlots() {
        const doctorId = doctorSelect.value;
        const date = dateInput.value;

        timeSelect.innerHTML = '<option value="" disabled selected>Loading available slots...</option>';
        timeSelect.disabled = true;
        slotAvailabilityDiv.textContent = '';
        submitBtn.disabled = true;
        loadingSpinner.style.display = 'block';

        if (doctorId && date) {
            fetch(`/get_available_slots?doctor_id=${doctorId}&date=${date}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Network response was not ok');
                    }
                    return response.json();
                })
                .then(data => {
                    loadingSpinner.style.display = 'none';
                    timeSelect.innerHTML = '<option value="" disabled selected>Select a time</option>';
                    if (data.error) {
                        timeSelect.innerHTML = '<option value="" disabled selected>Error loading slots</option>';
                    } else if (data.length === 0) {
                        timeSelect.innerHTML = '<option value="" disabled selected>No available slots</option>';
                    } else {
                        data.forEach(slot => {
                            const option = document.createElement('option');
                            option.value = slot;
                            option.textContent = slot;
                            timeSelect.appendChild(option);
                        });
                        timeSelect.disabled = false;
                    }
                })
                .catch(error => {
                    console.error('Error fetching available slots:', error);
                    loadingSpinner.style.display = 'none';
                    timeSelect.innerHTML = '<option value="" disabled selected>Error loading slots</option>';
                });
        } else {
            loadingSpinner.style.display = 'none';
        }
    }

    // Check slot availability (final confirmation before enabling submit)
    function checkSlotAvailability() {
        const doctorId = doctorSelect.value;
        const date = dateInput.value;
        const time = timeSelect.value;

        slotAvailabilityDiv.textContent = '';
        submitBtn.disabled = true;

        if (doctorId && date && time) {
            slotAvailabilityDiv.textContent = 'Checking final availability...';
            loadingSpinner.style.display = 'block';
            fetch(`/check_slot?doctor_id=${doctorId}&date=${date}&time=${encodeURIComponent(time)}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Network response was not ok');
                    }
                    return response.json();
                })
                .then(data => {
                    loadingSpinner.style.display = 'none';
                    if (data.available) {
                        slotAvailabilityDiv.textContent = 'Slot is available';
                        slotAvailabilityDiv.className = 'slot-available';
                        submitBtn.disabled = false;
                    } else {
                        slotAvailabilityDiv.textContent = 'Slot is unavailable';
                        slotAvailabilityDiv.className = 'slot-unavailable';
                        submitBtn.disabled = true;
                    }
                })
                .catch(error => {
                    console.error('Error checking slot availability:', error);
                    loadingSpinner.style.display = 'none';
                    slotAvailabilityDiv.textContent = 'Error checking availability';
                    slotAvailabilityDiv.className = 'slot-unavailable';
                    submitBtn.disabled = true;
                });
        } else {
            loadingSpinner.style.display = 'none';
        }
    }

    // Validate date (ensure it's between 2025-05-09 and 2026-05-09)
    dateInput.addEventListener('change', function () {
        const selectedDate = new Date(this.value);
        const minDate = new Date('2025-05-09');
        const maxDate = new Date('2026-05-09');

        if (selectedDate < minDate || selectedDate > maxDate) {
            alert('Please select a date between 2025-05-09 and 2026-05-09.');
            this.value = '';
            timeSelect.innerHTML = '<option value="" disabled selected>Select a date first</option>';
            timeSelect.disabled = true;
            slotAvailabilityDiv.textContent = '';
            submitBtn.disabled = true;
        }
    });

    // Ensure time slot is selected
    timeSelect.addEventListener('change', function () {
        if (!this.value) {
            alert('Please select a time slot.');
            slotAvailabilityDiv.textContent = '';
            submitBtn.disabled = true;
        }
    });

    // Add event listeners
    hospitalSelect.addEventListener('change', loadDepartments);
    departmentSelect.addEventListener('change', loadDoctors);
    doctorSelect.addEventListener('change', loadAvailableSlots);
    dateInput.addEventListener('change', loadAvailableSlots);
    timeSelect.addEventListener('change', checkSlotAvailability);
});