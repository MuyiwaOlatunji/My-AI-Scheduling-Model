document.addEventListener('DOMContentLoaded', function () {
    const hospitalSelect = document.getElementById('hospital');
    const departmentSelect = document.getElementById('department');
    const doctorSelect = document.getElementById('doctor');
    const dateInput = document.getElementById('date');
    const timeSelect = document.getElementById('time');
    const slotAvailabilityDiv = document.getElementById('slotAvailability');
    const submitBtn = document.getElementById('submitBtn');
    const loadingSpinner = document.getElementById('loadingSpinner');

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

    async function loadDepartments() {
        const hospitalId = hospitalSelect.value;
        resetDependentDropdowns();

        if (hospitalId) {
            departmentSelect.innerHTML = '<option value="" disabled selected>Loading departments...</option>';
            try {
                const response = await fetch(`/get_departments/${hospitalId}`);
                if (!response.ok) throw new Error('Network response was not ok');
                const data = await response.json();
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
            } catch (error) {
                console.error('Error fetching departments:', error);
                departmentSelect.innerHTML = '<option value="" disabled selected>Error loading departments</option>';
            }
        }
    }

    async function loadDoctors() {
        const departmentId = departmentSelect.value;
        doctorSelect.innerHTML = '<option value="" disabled selected>Loading doctors...</option>';
        doctorSelect.disabled = true;
        timeSelect.innerHTML = '<option value="" disabled selected>Select a date first</option>';
        timeSelect.disabled = true;
        slotAvailabilityDiv.textContent = '';
        submitBtn.disabled = true;

        if (departmentId) {
            try {
                const response = await fetch(`/get_doctors/${departmentId}`);
                if (!response.ok) throw new Error('Network response was not ok');
                const data = await response.json();
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
            } catch (error) {
                console.error('Error fetching doctors:', error);
                doctorSelect.innerHTML = '<option value="" disabled selected>Error loading doctors</option>';
            }
        }
    }

    async function loadAvailableSlots() {
        const doctorId = doctorSelect.value;
        const date = dateInput.value;

        timeSelect.innerHTML = '<option value="" disabled selected>Loading available slots...</option>';
        timeSelect.disabled = true;
        slotAvailabilityDiv.textContent = '';
        submitBtn.disabled = true;
        loadingSpinner.style.display = 'block';

        if (doctorId && date) {
            try {
                const response = await fetch(`/get_available_slots?doctor_id=${doctorId}&date=${date}`);
                if (!response.ok) throw new Error('Network response was not ok');
                const data = await response.json();
                loadingSpinner.style.display = 'none';
                timeSelect.innerHTML = '<option value="" disabled selected>Select a time</option>';
                if (data.error) {
                    timeSelect.innerHTML = '<option value="" disabled selected>Error loading slots</option>';
                    slotAvailabilityDiv.textContent = data.error;
                    slotAvailabilityDiv.className = 'error-message';
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
            } catch (error) {
                console.error('Error fetching available slots:', error);
                loadingSpinner.style.display = 'none';
                timeSelect.innerHTML = '<option value="" disabled selected>Error loading slots</option>';
                slotAvailabilityDiv.textContent = 'Error loading available slots';
                slotAvailabilityDiv.className = 'error-message';
            }
        } else {
            loadingSpinner.style.display = 'none';
        }
    }

    async function checkSlotAvailability() {
        const doctorId = doctorSelect.value;
        const date = dateInput.value;
        const time = timeSelect.value;

        slotAvailabilityDiv.textContent = '';
        submitBtn.disabled = true;

        if (doctorId && date && time) {
            slotAvailabilityDiv.textContent = 'Checking final availability...';
            slotAvailabilityDiv.className = '';
            loadingSpinner.style.display = 'block';
            try {
                const response = await fetch(`/check_slot?doctor_id=${doctorId}&date=${date}&time=${encodeURIComponent(time)}`);
                if (!response.ok) throw new Error('Network response was not ok');
                const data = await response.json();
                loadingSpinner.style.display = 'none';
                if (data.available) {
                    slotAvailabilityDiv.textContent = 'Slot is available';
                    slotAvailabilityDiv.className = 'slot-available';
                    submitBtn.disabled = false;
                } else {
                    slotAvailabilityDiv.textContent = data.error || 'Slot is unavailable';
                    slotAvailabilityDiv.className = 'slot-unavailable';
                    submitBtn.disabled = true;
                }
            } catch (error) {
                console.error('Error checking slot availability:', error);
                loadingSpinner.style.display = 'none';
                slotAvailabilityDiv.textContent = 'Error checking availability';
                slotAvailabilityDiv.className = 'error-message';
                submitBtn.disabled = true;
            }
        } else {
            loadingSpinner.style.display = 'none';
        }
    }

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

    timeSelect.addEventListener('change', function () {
        if (!this.value) {
            alert('Please select a time slot.');
            slotAvailabilityDiv.textContent = '';
            submitBtn.disabled = true;
        }
    });

    hospitalSelect.addEventListener('change', loadDepartments);
    departmentSelect.addEventListener('change', loadDoctors);
    doctorSelect.addEventListener('change', loadAvailableSlots);
    dateInput.addEventListener('change', loadAvailableSlots);
    timeSelect.addEventListener('change', checkSlotAvailability);
});

document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.auto-reschedule-btn').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const apptId = this.getAttribute('data-appt-id');
            if (confirm('Are you sure you want to auto-reschedule this appointment?')) {
                fetch(`/auto_reschedule/${apptId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Network response was not ok: ' + response.statusText);
                    }
                    return response.json();
                })
                .then(data => {
                    alert(data.message);
                    if (data.status === 'success') {
                        location.reload();
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('An error occurred while auto-rescheduling: ' + error.message);
                });
            }
        });
    });
});