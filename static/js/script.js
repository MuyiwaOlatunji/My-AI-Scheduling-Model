document.addEventListener('DOMContentLoaded', function () {
    // Booking Form Functions
    const hospitalSelect = document.getElementById('hospital');
    const departmentSelect = document.getElementById('department');
    const doctorSelect = document.getElementById('doctor');
    const dateInput = document.getElementById('date');
    const timeSelect = document.getElementById('time');
    const slotAvailabilityDiv = document.getElementById('slotAvailability');
    const submitBtn = document.getElementById('submitBtn');
    const loadingSpinner = document.getElementById('loadingSpinner');

    if (hospitalSelect) {
        hospitalSelect.addEventListener('change', loadDepartments);
    }
    if (departmentSelect) {
        departmentSelect.addEventListener('change', loadDoctors);
    }
    if (doctorSelect) {
        doctorSelect.addEventListener('change', loadAvailableSlots);
    }
    if (dateInput) {
        dateInput.addEventListener('change', function () {
            const selectedDate = new Date(this.value);
            const currentDate = new Date();
            const maxDate = new Date(currentDate.setFullYear(currentDate.getFullYear() + 1));
            currentDate.setDate(currentDate.getDate() - currentDate.getFullYear() - 1); // Reset to today
            if (selectedDate < currentDate || selectedDate > maxDate) {
                alert(`Please select a date between ${currentDate.toISOString().split('T')[0]} and ${maxDate.toISOString().split('T')[0]}.`);
                this.value = '';
                resetTimeSelect();
            } else {
                loadAvailableSlots();
            }
        });
    }
    if (timeSelect) {
        timeSelect.addEventListener('change', checkSlotAvailability);
    }

    async function loadDepartments() {
        const hospitalId = hospitalSelect.value;
        resetDependentDropdowns();
        if (!hospitalId) return;
        departmentSelect.innerHTML = '<option value="" disabled selected>Loading...</option>';
        try {
            const response = await fetch(`/get_departments/${hospitalId}`);
            const data = await response.json();
            departmentSelect.innerHTML = '<option value="" disabled selected>Select a department</option>';
            data.forEach(dept => {
                const option = new Option(dept[1], dept[0]);
                departmentSelect.appendChild(option);
            });
            departmentSelect.disabled = false;
        } catch (error) {
            departmentSelect.innerHTML = '<option value="" disabled selected>Error loading</option>';
            console.error('Error:', error);
        }
    }

    async function loadDoctors() {
        const departmentId = departmentSelect.value;
        if (!departmentId) return;
        doctorSelect.innerHTML = '<option value="" disabled selected>Loading...</option>';
        try {
            const response = await fetch(`/get_doctors/${departmentId}`);
            const data = await response.json();
            doctorSelect.innerHTML = '<option value="" disabled selected>Select a doctor</option>';
            data.forEach(doc => {
                const option = new Option(doc[1], doc[0]);
                doctorSelect.appendChild(option);
            });
            doctorSelect.disabled = false;
        } catch (error) {
            doctorSelect.innerHTML = '<option value="" disabled selected>Error loading</option>';
            console.error('Error:', error);
        }
    }

    async function loadAvailableSlots() {
        const doctorId = doctorSelect.value;
        const date = dateInput.value;
        if (!doctorId || !date) return;
        timeSelect.innerHTML = '<option value="" disabled selected>Loading...</option>';
        timeSelect.disabled = true;
        slotAvailabilityDiv.textContent = '';
        submitBtn.disabled = true;
        loadingSpinner.style.display = 'block';
        try {
            const response = await fetch(`/get_available_slots?doctor_id=${doctorId}&date=${date}`);
            const data = await response.json();
            loadingSpinner.style.display = 'none';
            timeSelect.innerHTML = '<option value="" disabled selected>Select a time</option>';
            if (data.error) {
                slotAvailabilityDiv.textContent = data.error;
                slotAvailabilityDiv.className = 'text-danger';
            } else if (!data.length) {
                timeSelect.innerHTML = '<option value="" disabled selected>No slots available</option>';
            } else {
                data.forEach(slot => {
                    const option = new Option(slot, slot);
                    timeSelect.appendChild(option);
                });
                timeSelect.disabled = false;
            }
        } catch (error) {
            loadingSpinner.style.display = 'none';
            timeSelect.innerHTML = '<option value="" disabled selected>Error loading</option>';
            console.error('Error:', error);
        }
    }

    async function checkSlotAvailability() {
        const doctorId = doctorSelect.value;
        const date = dateInput.value;
        const time = timeSelect.value;
        if (!doctorId || !date || !time) return;
        slotAvailabilityDiv.textContent = '';
        submitBtn.disabled = true;
        loadingSpinner.style.display = 'block';
        try {
            const response = await fetch(`/check_slot?doctor_id=${doctorId}&date=${date}&time=${encodeURIComponent(time)}`);
            const data = await response.json();
            loadingSpinner.style.display = 'none';
            slotAvailabilityDiv.textContent = data.available ? 'Slot available' : 'Slot unavailable';
            slotAvailabilityDiv.className = data.available ? 'text-success' : 'text-danger';
            submitBtn.disabled = !data.available;
        } catch (error) {
            loadingSpinner.style.display = 'none';
            slotAvailabilityDiv.textContent = 'Error checking slot';
            slotAvailabilityDiv.className = 'text-danger';
            console.error('Error:', error);
        }
    }

    function resetDependentDropdowns() {
        departmentSelect.innerHTML = '<option value="" disabled selected>Select a department</option>';
        departmentSelect.disabled = true;
        doctorSelect.innerHTML = '<option value="" disabled selected>Select a doctor</option>';
        doctorSelect.disabled = true;
        resetTimeSelect();
    }

    function resetTimeSelect() {
        timeSelect.innerHTML = '<option value="" disabled selected>Select a date first</option>';
        timeSelect.disabled = true;
        slotAvailabilityDiv.textContent = '';
        submitBtn.disabled = true;
    }

    // Hospital Registration Functions
    window.addDepartment = function() {
        const departmentsDiv = document.getElementById('departments');
        const deptCount = parseInt(departmentsDiv.getAttribute('data-dept-count'));
        const newDeptIndex = deptCount;
        departmentsDiv.setAttribute('data-dept-count', deptCount + 1);
        const firstDept = departmentsDiv.querySelector('.department');
        const newDept = firstDept.cloneNode(true);
        newDept.setAttribute('data-dept-index', newDeptIndex);
        newDept.setAttribute('data-doctor-count', 1);
        newDept.querySelectorAll('input, select').forEach(input => {
            input.name = input.name.replace(/\[\d+\]/, `[${newDeptIndex}]`);
            input.value = '';
        });
        const doctorsDiv = newDept.querySelector('.doctors');
        doctorsDiv.innerHTML = '';
        addDoctor(newDeptIndex);
        departmentsDiv.appendChild(newDept);
    };

    window.addDoctor = function(deptIndex) {
        const deptDiv = document.querySelector(`.department[data-dept-index="${deptIndex}"]`);
        const doctorCount = parseInt(deptDiv.getAttribute('data-doctor-count'));
        const newDoctorIndex = doctorCount;
        deptDiv.setAttribute('data-doctor-count', doctorCount + 1);
        const firstDoctor = document.querySelector('.department[data-dept-index="0"] .doctor');
        const newDoctor = firstDoctor.cloneNode(true);
        newDoctor.querySelectorAll('input, select').forEach(input => {
            input.name = input.name.replace(/\[\d+\]\[\d+\]/, `[${deptIndex}][${newDoctorIndex}]`);
            input.value = '';
        });
        deptDiv.querySelector('.doctors').appendChild(newDoctor);
    };

    // Admin Dashboard Auto-Reschedule
    document.querySelectorAll('.auto-reschedule-btn').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const apptId = this.getAttribute('data-appt-id');
            if (confirm('Are you sure you want to auto-reschedule this appointment?')) {
                fetch(`/auto_reschedule/${apptId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    if (data.status === 'success') location.reload();
                })
                .catch(error => alert('Error: ' + error.message));
            }
        });
    });

    // Alert Fading
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.classList.add('fade');
            setTimeout(() => alert.remove(), 500);
        }, 8000);
    });
});