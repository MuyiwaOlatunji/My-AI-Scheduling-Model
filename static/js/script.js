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
    const toggleProfileBtn = document.getElementById('toggleProfileBtn');
    const profileForm = document.getElementById('profileForm');

    if (hospitalSelect) {
        hospitalSelect.addEventListener('change', loadDepartments);
        departmentSelect.disabled = true;
        doctorSelect.disabled = true;
        timeSelect.disabled = true;
    }
    if (departmentSelect) {
        departmentSelect.addEventListener('change', loadDoctors);
    }
    if (doctorSelect && dateInput) {
        doctorSelect.addEventListener('change', loadAvailableSlots);
        dateInput.addEventListener('change', loadAvailableSlots);
    }
    if (timeSelect) {
        timeSelect.addEventListener('change', checkSlotAvailability);
    }
    if (toggleProfileBtn && profileForm) {
        toggleProfileBtn.addEventListener('click', function () {
            profileForm.classList.toggle('show');
            this.innerHTML = profileForm.classList.contains('show')
                ? '<i class="fas fa-user-edit"></i> Hide Profile Update'
                : '<i class="fas fa-user-edit"></i> Update Profile';
        });
    }

    async function loadDepartments() {
        const hospitalId = hospitalSelect.value;
        resetDependentDropdowns();
        if (!hospitalId) {
            departmentSelect.disabled = true;
            return;
        }
        departmentSelect.innerHTML = '<option value="" disabled selected>Loading...</option>';
        try {
            const response = await fetch(`/get_departments/${hospitalId}`);
            if (!response.ok) throw new Error('Failed to fetch departments');
            const data = await response.json();
            departmentSelect.innerHTML = '<option value="" disabled selected>Select a department</option>';
            data.forEach(dept => {
                const option = new Option(dept.name, dept.id); // Adjusted to match JSON structure
                departmentSelect.appendChild(option);
            });
            departmentSelect.disabled = false;
        } catch (error) {
            departmentSelect.innerHTML = '<option value="" disabled selected>Error loading departments</option>';
            departmentSelect.disabled = true;
            console.error('Error loading departments:', error);
        }
    }

    async function loadDoctors() {
        const departmentId = departmentSelect.value;
        doctorSelect.innerHTML = '<option value="" disabled selected>Loading...</option>';
        doctorSelect.disabled = true;
        if (!departmentId) return;
        try {
            const response = await fetch(`/get_doctors/${departmentId}`);
            if (!response.ok) throw new Error('Failed to fetch doctors');
            const data = await response.json();
            doctorSelect.innerHTML = '<option value="" disabled selected>Select a doctor</option>';
            data.forEach(doc => {
                const option = new Option(doc.name, doc.id); // Adjusted to match JSON structure
                doctorSelect.appendChild(option);
            });
            doctorSelect.disabled = false;
        } catch (error) {
            doctorSelect.innerHTML = '<option value="" disabled selected>Error loading doctors</option>';
            doctorSelect.disabled = true;
            console.error('Error loading doctors:', error);
        }
    }

    async function loadAvailableSlots() {
        const doctorId = doctorSelect.value;
        const date = dateInput.value;
        if (!doctorId || !date) {
            resetTimeSelect();
            return;
        }
        timeSelect.innerHTML = '<option value="" disabled selected>Loading...</option>';
        timeSelect.disabled = true;
        slotAvailabilityDiv.textContent = '';
        submitBtn.disabled = true;
        loadingSpinner.style.display = 'block';
        try {
            const response = await fetch(`/get_available_slots?doctor_id=${doctorId}&date=${date}`);
            if (!response.ok) throw new Error('Failed to fetch slots');
            const data = await response.json();
            loadingSpinner.style.display = 'none';
            timeSelect.innerHTML = '<option value="" disabled selected>Select a time</option>';
            if (data.error) {
                slotAvailabilityDiv.textContent = data.error;
                slotAvailabilityDiv.className = 'slot-unavailable';
                timeSelect.innerHTML = '<option value="" disabled selected>No slots available</option>';
            } else if (!data.length) {
                slotAvailabilityDiv.textContent = 'No slots available';
                slotAvailabilityDiv.className = 'slot-unavailable';
                timeSelect.innerHTML = '<option value="" disabled selected>No slots available</option>';
            } else {
                data.forEach(slot => {
                    const option = new Option(slot, slot);
                    timeSelect.appendChild(option);
                });
                timeSelect.disabled = false;
                slotAvailabilityDiv.textContent = 'Please select a time';
                slotAvailabilityDiv.className = 'slot-available';
                submitBtn.disabled = false;
            }
        } catch (error) {
            loadingSpinner.style.display = 'none';
            timeSelect.innerHTML = '<option value="" disabled selected>Error loading slots</option>';
            slotAvailabilityDiv.textContent = 'Error loading slots';
            slotAvailabilityDiv.className = 'slot-unavailable';
            console.error('Error loading slots:', error);
        }
    }

    async function checkSlotAvailability() {
        const doctorId = doctorSelect.value;
        const date = dateInput.value;
        const time = timeSelect.value;
        if (!doctorId || !date || !time) {
            submitBtn.disabled = true;
            return;
        }
        try {
            const response = await fetch(`/check_slot?doctor_id=${doctorId}&date=${date}&time=${time}`);
            if (!response.ok) throw new Error('Failed to check slot');
            const data = await response.json();
            slotAvailabilityDiv.textContent = data.available ? 'Slot available' : 'Slot unavailable';
            slotAvailabilityDiv.className = data.available ? 'slot-available' : 'slot-unavailable';
            submitBtn.disabled = !data.available;
        } catch (error) {
            slotAvailabilityDiv.textContent = 'Error checking slot';
            slotAvailabilityDiv.className = 'slot-unavailable';
            submitBtn.disabled = true;
            console.error('Error checking slot:', error);
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
        const deptCount = parseInt(departmentsDiv.getAttribute('data-dept-count') || 0);
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
        const doctorCount = parseInt(deptDiv.getAttribute('data-doctor-count') || 0);
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

    // Alert Fading
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.classList.add('fade');
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });

    // Password Toggle
    const togglePassword = document.querySelector('#togglePassword');
    const password = document.querySelector('#password');
    if (togglePassword && password) {
        togglePassword.addEventListener('click', function () {
            const type = password.getAttribute('type') === 'password' ? 'text' : 'password';
            password.setAttribute('type', type);
            this.classList.toggle('fa-eye');
            this.classList.toggle('fa-eye-slash');
        });
    }
});