document.addEventListener('DOMContentLoaded', function () {
    // Get references to the dropdown elements
    const hospitalSelect = document.getElementById('hospital');
    const departmentSelect = document.getElementById('department');
    const doctorSelect = document.getElementById('doctor');
    const dateInput = document.getElementById('date');
    const timeSelect = document.getElementById('time');

    // Function to reset and disable dependent dropdowns
    function resetDependentDropdowns() {
        departmentSelect.innerHTML = '<option value="" disabled selected>Pick a hospital first</option>';
        departmentSelect.disabled = true;
        doctorSelect.innerHTML = '<option value="" disabled selected>Pick a department first</option>';
        doctorSelect.disabled = true;
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

    // Add event listeners
    hospitalSelect.addEventListener('change', loadDepartments);
    departmentSelect.addEventListener('change', loadDoctors);

    // Validate date (prevent past dates)
    dateInput.addEventListener('change', function () {
        const selectedDate = new Date(this.value);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        if (selectedDate < today) {
            alert('Please select a date that is today or in the future.');
            this.value = '';
        }
    });

    // Ensure time slot is selected
    timeSelect.addEventListener('change', function () {
        if (!this.value) {
            alert('Please select a time slot.');
        }
    });
});