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
    const healthChallengeInput = document.getElementById('health_challenge');

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
    if (submitBtn && healthChallengeInput) {
        submitBtn.addEventListener('click', function (e) {
            if (healthChallengeInput.value.trim().length > 255) {
                e.preventDefault();
                alert('Health challenge description must be 255 characters or less.');
                healthChallengeInput.focus();
            }
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
                const option = new Option(dept[1], dept[0]);
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
                const option = new Option(doc[1], doc[0]);
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
            timeSelect.innerHTML = '';
            timeSelect.disabled = true;
            return;
        }
        timeSelect.innerHTML = '<option value="" disabled selected>Loading...</option>';
        timeSelect.disabled = true;
        try {
            const response = await fetch(`/get_available_slots?doctor_id=${doctorId}&date=${date}`);
            if (!response.ok) throw new Error('Failed to fetch slots');
            const slots = await response.json();
            timeSelect.innerHTML = '<option value="" disabled selected>Select a time</option>';
            slots.forEach(slot => {
                const option = new Option(slot, slot);
                timeSelect.appendChild(option);
            });
            timeSelect.disabled = false;
        } catch (error) {
            timeSelect.innerHTML = '<option value="" disabled selected>Error loading slots</option>';
            timeSelect.disabled = true;
            console.error('Error loading slots:', error);
        }
    }

    async function checkSlotAvailability() {
        const doctorId = doctorSelect.value;
        const date = dateInput.value;
        const time = timeSelect.value;
        if (!doctorId || !date || !time) {
            slotAvailabilityDiv.textContent = '';
            return;
        }
        try {
            const response = await fetch(`/check_slot?doctor_id=${doctorId}&date=${date}&time=${time}`);
            if (!response.ok) throw new Error('Failed to check slot');
            const data = await response.json();
            slotAvailabilityDiv.textContent = data.available
                ? 'Slot available'
                : 'Slot unavailable';
            slotAvailabilityDiv.className = data.available
                ? 'slot-available'
                : 'slot-unavailable';
            submitBtn.disabled = !data.available;
        } catch (error) {
            slotAvailabilityDiv.textContent = 'Error checking slot';
            slotAvailabilityDiv.className = 'error-message';
            submitBtn.disabled = true;
            console.error('Error checking slot:', error);
        }
    }

    function resetDependentDropdowns() {
        departmentSelect.innerHTML = '<option value="" disabled selected>Select a department</option>';
        doctorSelect.innerHTML = '<option value="" disabled selected>Select a doctor</option>';
        timeSelect.innerHTML = '';
        departmentSelect.disabled = true;
        doctorSelect.disabled = true;
        timeSelect.disabled = true;
        slotAvailabilityDiv.textContent = '';
    }

    // Manage Departments Functions
    const addDoctorButtons = document.querySelectorAll('.add-doctor-btn');
    const addDoctorCards = document.querySelectorAll('.add-doctor-card');
    const editDoctorButtons = document.querySelectorAll('.edit-doctor-btn');
    const deleteDoctorButtons = document.querySelectorAll('.delete-doctor-btn');
    const deleteDeptButtons = document.querySelectorAll('.delete-dept-btn');

    addDoctorButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            const card = this.nextElementSibling;
            card.classList.add('show');
            card.querySelector('form').addEventListener('submit', function (e) {
                e.preventDefault();
                const formData = new FormData(this);
                formData.append('add_doctor', 'true');
                fetch('/manage_departments', {
                    method: 'POST',
                    body: formData
                }).then(response => response.json())
                  .then(data => {
                      if (data.success) {
                          location.reload();
                      } else {
                          showAlert(data.message, 'danger');
                      }
                  })
                  .catch(error => {
                      console.error('Error adding doctor:', error);
                      showAlert('Failed to add doctor', 'danger');
                  });
            });
        });
    });

    editDoctorButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            const doctorId = this.dataset.doctorId;
            const card = this.closest('.department-card').querySelector('.add-doctor-card');
            card.classList.add('show');
            const form = card.querySelector('form');
            form.querySelector('[name="doctor_id"]').value = doctorId;
            form.querySelector('[name="doctor_name"]').value = this.dataset.doctorName || '';
            form.querySelector('[name="doctor_gender"]').value = this.dataset.doctorGender || 'M';
            const schedule = this.dataset.doctorSchedule || 'mon-fri 9-17';
            const [days, times] = schedule.split(' ');
            const [startDay, endDay] = days.split('-');
            const [startTime, endTime] = times.split('-');
            form.querySelector('[name="start_day"]').value = startDay;
            form.querySelector('[name="end_day"]').value = endDay;
            form.querySelector('[name="start_time"]').value = startTime;
            form.querySelector('[name="end_time"]').value = endTime;
            form.addEventListener('submit', function (e) {
                e.preventDefault();
                const formData = new FormData(this);
                formData.append('edit_doctor', 'true');
                fetch('/manage_departments', {
                    method: 'POST',
                    body: formData
                }).then(response => response.json())
                  .then(data => {
                      if (data.success) {
                          location.reload();
                      } else {
                          showAlert(data.message, 'danger');
                      }
                  })
                  .catch(error => {
                      console.error('Error editing doctor:', error);
                      showAlert('Failed to edit doctor', 'danger');
                  });
            });
        });
    });

    deleteDoctorButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            if (confirm('Are you sure you want to delete this doctor?')) {
                const doctorId = this.dataset.doctorId;
                const formData = new FormData();
                formData.append('delete_doctor', 'true');
                formData.append('doctor_id', doctorId);
                fetch('/manage_departments', {
                    method: 'POST',
                    body: formData
                }).then(response => response.json())
                  .then(data => {
                      if (data.success) {
                          location.reload();
                      } else {
                          showAlert(data.message, 'danger');
                      }
                  })
                  .catch(error => {
                      console.error('Error deleting doctor:', error);
                      showAlert('Failed to delete doctor', 'danger');
                  });
            }
        });
    });

    deleteDeptButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            if (confirm('Are you sure you want to delete this department?')) {
                const deptId = this.dataset.deptId;
                const formData = new FormData();
                formData.append('delete_dept', 'true');
                formData.append('dept_id', deptId);
                fetch('/manage_departments', {
                    method: 'POST',
                    body: formData
                }).then(response => response.json())
                  .then(data => {
                      if (data.success) {
                          location.reload();
                      } else {
                          showAlert(data.message, 'danger');
                      }
                  })
                  .catch(error => {
                      console.error('Error deleting department:', error);
                      showAlert('Failed to delete department', 'danger');
                  });
            }
        });
    });

    // Hospital Admin Search
    const searchInput = document.getElementById('searchInput');
    const searchTypeSelect = document.getElementById('searchType');
    const searchResultsDiv = document.getElementById('searchResults');
    if (searchInput && searchTypeSelect) {
        searchInput.addEventListener('input', async function (e) {
            const query = e.target.value.trim();
            const type = searchTypeSelect.value;
            if (query.length < 2) {
                if (searchResultsDiv) searchResultsDiv.innerHTML = '';
                return;
            }
            try {
                const response = await fetch(`/search_appointments?search=${encodeURIComponent(query)}&search_type=${type}`);
                if (!response.ok) throw new Error('Failed to fetch search results');
                const data = await response.json();
                if (searchResultsDiv) {
                    searchResultsDiv.innerHTML = data.map(appt => `<p>${appt.patient_name} - ${appt.date}</p>`).join('');
                }
            } catch (error) {
                console.error('Error searching appointments:', error);
                if (searchResultsDiv) searchResultsDiv.innerHTML = '<p>Error loading results</p>';
            }
        });
        searchTypeSelect.addEventListener('change', async function () {
            const query = searchInput.value.trim();
            const type = this.value;
            if (query.length < 2) {
                if (searchResultsDiv) searchResultsDiv.innerHTML = '';
                return;
            }
            try {
                const response = await fetch(`/search_appointments?search=${encodeURIComponent(query)}&search_type=${type}`);
                if (!response.ok) throw new Error('Failed to fetch search results');
                const data = await response.json();
                if (searchResultsDiv) {
                    searchResultsDiv.innerHTML = data.map(appt => `<p>${appt.patient_name} - ${appt.date}</p>`).join('');
                }
            } catch (error) {
                console.error('Error searching appointments:', error);
                if (searchResultsDiv) searchResultsDiv.innerHTML = '<p>Error loading results</p>';
            }
        });
    }

    // Patient Dashboard Actions
    const cancelButtons = document.querySelectorAll('.cancel-btn');
    const rescheduleButtons = document.querySelectorAll('.reschedule-btn');
    cancelButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            const apptId = this.dataset.apptId;
            if (confirm('Are you sure you want to cancel this appointment?')) {
                fetch(`/cancel_appointment/${apptId}`, {
                    method: 'GET'
                }).then(response => response.ok ? location.reload() : showAlert('Failed to cancel appointment', 'danger'))
                  .catch(error => console.error('Error:', error));
            }
        });
    });

    rescheduleButtons.forEach(btn => {
        btn.addEventListener('click', function () {
            const apptId = this.dataset.apptId;
            const card = this.nextElementSibling;
            card.classList.add('show');
            const form = card.querySelector('form');
            form.addEventListener('submit', function (e) {
                e.preventDefault();
                const formData = new FormData(this);
                fetch(`/reschedule_patient/${apptId}`, {
                    method: 'POST',
                    body: formData
                }).then(response => response.ok ? location.reload() : showAlert('Failed to reschedule appointment', 'danger'))
                  .catch(error => console.error('Error:', error));
            });
        });
    });

    // Profile Update
    const profileFormSubmit = document.getElementById('profileFormSubmit');
    if (profileFormSubmit) {
        profileFormSubmit.addEventListener('submit', function (e) {
            e.preventDefault();
            const formData = new FormData(this);
            fetch('/update_profile', {
                method: 'POST',
                body: formData
            }).then(response => response.ok ? location.reload() : showAlert('Failed to update profile', 'danger'))
              .catch(error => console.error('Error:', error));
        });
    }

    // Alert Function with 10-second timeout
    function showAlert(message, type) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type}`;
        alertDiv.textContent = message;
        document.body.appendChild(alertDiv);
        setTimeout(() => alertDiv.classList.add('fade'), 9000); // Start fading at 9 seconds
        setTimeout(() => alertDiv.remove(), 10000); // Remove after 10 seconds
    }
});