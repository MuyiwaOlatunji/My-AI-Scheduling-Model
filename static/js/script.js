// Helper function to get CSRF token from hidden input or meta tag
function getCsrfToken() {
    const hiddenInput = document.querySelector('input[name="csrf_token"]');
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    return hiddenInput ? hiddenInput.value : (metaTag ? metaTag.getAttribute('content') : null);
}

// Helper function to format schedule
function formatSchedule(schedule) {
    if (!schedule) return 'Not set';
    try {
        const parts = schedule.toLowerCase().split(' ');
        if (parts.length !== 2) return schedule;

        const days = parts[0].split('-');
        const times = parts[1].split('-');
        if (days.length !== 2 || times.length !== 2) return schedule;

        const dayMap = {
            'mon': 'Monday', 'tue': 'Tuesday', 'wed': 'Wednesday',
            'thu': 'Thursday', 'fri': 'Friday', 'sat': 'Saturday', 'sun': 'Sunday'
        };

        const startDay = dayMap[days[0]] || days[0];
        const endDay = dayMap[days[1]] || days[1];

        const formatTime = (timeStr) => {
            if (!timeStr) return '';
            let hour, minute;
            if (timeStr.includes(':')) {
                [hour, minute] = timeStr.split(':').map(Number);
            } else {
                hour = parseInt(timeStr.substring(0, 2));
                minute = parseInt(timeStr.substring(2)) || 0;
            }
            if (isNaN(hour)) hour = 0;
            if (isNaN(minute)) minute = 0;
            hour = Math.max(0, Math.min(23, hour));
            minute = Math.max(0, Math.min(59, minute));
            const period = hour >= 12 ? 'PM' : 'AM';
            const displayHour = hour % 12 || 12;
            return `${displayHour}:${minute.toString().padStart(2, '0')} ${period}`;
        };

        const startTime = formatTime(times[0]);
        const endTime = formatTime(times[1]);
        return `${startDay}-${endDay}, ${startTime} - ${endTime}`;
    } catch (e) {
        console.error('Error formatting schedule:', e);
        return schedule;
    }
}

// Global alert function
function showAlert(message, type) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} show`;
    alertDiv.innerHTML = `<span>${message}</span><button class="alert-close">&times;</button>`;
    document.body.appendChild(alertDiv);

    const closeBtn = alertDiv.querySelector('.alert-close');
    closeBtn.addEventListener('click', () => {
        alertDiv.classList.remove('show');
        alertDiv.classList.add('hide');
        setTimeout(() => alertDiv.remove(), 300);
    });

    const timeout = setTimeout(() => {
        alertDiv.classList.remove('show');
        alertDiv.classList.add('hide');
        setTimeout(() => alertDiv.remove(), 300);
    }, 6000);

    alertDiv.addEventListener('mouseenter', () => clearTimeout(timeout));
    alertDiv.addEventListener('mouseleave', () => {
        setTimeout(() => {
            alertDiv.classList.remove('show');
            alertDiv.classList.add('hide');
            setTimeout(() => alertDiv.remove(), 300);
        }, 3000);
    });
}

// Custom confirmation dialog
function showConfirm(message, callback) {
    const confirmDiv = document.createElement('div');
    confirmDiv.className = 'confirm-dialog';
    confirmDiv.innerHTML = `
        <div class="confirm-content">
            <p>${message}</p>
            <div class="confirm-buttons">
                <button class="btn btn-primary confirm-yes">Yes</button>
                <button class="btn btn-secondary confirm-no">No</button>
            </div>
        </div>
    `;
    document.body.appendChild(confirmDiv);

    confirmDiv.querySelector('.confirm-yes').addEventListener('click', () => {
        callback(true);
        confirmDiv.remove();
    });

    confirmDiv.querySelector('.confirm-no').addEventListener('click', () => {
        callback(false);
        confirmDiv.remove();
    });
}

// Delete Hospital Confirmation
function setupHospitalDeletion() {
    const modal = document.getElementById('deleteHospitalModal');
    const deleteButtons = document.querySelectorAll('.delete-hospital-btn');
    const confirmBtn = document.getElementById('confirmDeleteBtn');
    const cancelBtn = document.getElementById('cancelDeleteBtn');
    const closeBtn = document.querySelector('#deleteHospitalModal .close-modal');
    const deleteForm = document.getElementById('deleteHospitalForm');

    if (!modal || !confirmBtn || !cancelBtn || !closeBtn || !deleteForm) {
        console.warn('Delete hospital modal elements missing');
        return;
    }

    let currentHospitalId = null;

    deleteButtons.forEach(button => {
        button.addEventListener('click', function() {
            currentHospitalId = this.getAttribute('data-hospital-id');
            modal.style.display = 'block';
        });
    });

    confirmBtn.addEventListener('click', async function() {
        if (currentHospitalId) {
            try {
                const response = await fetch(`/delete_hospital/${currentHospitalId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': getCsrfToken()
                    },
                    body: JSON.stringify({ csrf_token: getCsrfToken() })
                });

                if (!response.ok) {
                    throw new Error(`Failed to delete hospital: ${response.status}`);
                }

                modal.style.display = 'none';
                currentHospitalId = null;
                window.location.reload();
            } catch (error) {
                console.error('Error deleting hospital:', error);
                showAlert('Error deleting hospital: ' + error.message, 'danger');
            }
        }
    });

    function closeModal() {
        modal.style.display = 'none';
        currentHospitalId = null;
    }

    cancelBtn.addEventListener('click', closeModal);
    closeBtn.addEventListener('click', closeModal);

    window.addEventListener('click', function(event) {
        if (event.target === modal) {
            closeModal();
        }
    });
}

// Load doctors for selected department
async function loadDoctorsForDepartment() {
    const deptId = document.getElementById('departmentSelect')?.value;
    const doctorManagementSection = document.getElementById('doctorManagementSection');
    const doctorList = document.getElementById('doctorList');

    if (!deptId || !doctorManagementSection || !doctorList) {
        if (doctorManagementSection) doctorManagementSection.style.display = 'none';
        return;
    }

    try {
        doctorManagementSection.style.display = 'block';
        doctorList.innerHTML = '<tr><td colspan="4" class="text-center">Loading doctors...</td></tr>';

        const response = await fetch(`/api/departments/${deptId}/doctors`, {
            headers: {
                'X-CSRF-Token': getCsrfToken()
            }
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error: ${response.status}`);
        }

        const doctors = await response.json();
        if (!Array.isArray(doctors)) throw new Error('Invalid data format received');

        doctorList.innerHTML = '';

        if (doctors.length === 0) {
            doctorList.innerHTML = '<tr><td colspan="4" class="text-center">No doctors found</td></tr>';
            return;
        }

        doctors.forEach(doc => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${doc.name || 'N/A'}</td>
                <td>${doc.gender === 'M' ? 'Male' : doc.gender === 'F' ? 'Female' : 'Other'}</td>
                <td>${formatSchedule(doc.schedule)}</td>
                <td class="actions">
                    <button class="btn btn-sm btn-warning" onclick="editDoctor(${doc.id})">
                        <i class="fas fa-edit"></i> Edit
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="confirmDeleteDoctor(${doc.id}, '${doc.name.replace(/'/g, "\\'")}')">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </td>
            `;
            doctorList.appendChild(row);
        });

    } catch (error) {
        console.error('Error loading doctors:', error);
        doctorList.innerHTML = `
            <tr>
                <td colspan="4" class="text-center error">
                    Error loading doctors. <button onclick="loadDoctorsForDepartment()" class="btn btn-sm btn-primary mt-2">
                        <i class="fas fa-sync-alt"></i> Retry
                    </button>
                </td>
            </tr>
        `;
        showAlert('Error loading doctors: ' + error.message, 'danger');
    }
}

// Add doctor function
async function addDoctor() {
    const form = document.getElementById('addDoctorForm');
    if (!form) {
        console.error('Add doctor form not found');
        return;
    }

    const formData = {
        department_id: form.querySelector('[name="department_id"]').value,
        name: form.querySelector('[name="name"]').value.trim(),
        gender: form.querySelector('[name="gender"]').value,
        start_day: form.querySelector('[name="start_day"]').value.toLowerCase(),
        end_day: form.querySelector('[name="end_day"]').value.toLowerCase(),
        start_time: form.querySelector('[name="start_time"]').value,
        end_time: form.querySelector('[name="end_time"]').value,
        csrf_token: getCsrfToken()
    };

    if (!formData.department_id || !formData.name || !formData.gender || !formData.start_day ||
        !formData.end_day || !formData.start_time || !formData.end_time || !formData.csrf_token) {
        showAlert('Please fill all required fields', 'danger');
        return;
    }

    try {
        const response = await fetch('/add_doctor', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': formData.csrf_token
            },
            body: JSON.stringify(formData)
        });

        const result = await response.json();
        if (!response.ok) throw new Error(result.message || 'Failed to add doctor');

        if (result.success) {
            showAlert('Doctor added successfully', 'success');
            document.getElementById('addDoctorCard').style.display = 'none';
            form.reset();
            await loadDoctorsForDepartment();
        } else {
            throw new Error(result.message || 'Failed to add doctor');
        }
    } catch (error) {
        console.error('Error adding doctor:', error);
        showAlert('Error adding doctor: ' + error.message, 'danger');
    }
}

// Delete doctor with custom confirmation
async function confirmDeleteDoctor(doctorId, doctorName) {
    showConfirm(`Are you sure you want to delete Dr. ${doctorName}?`, async (confirmed) => {
        if (confirmed) {
            try {
                const response = await fetch(`/delete_doctor/${doctorId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': getCsrfToken()
                    },
                    body: JSON.stringify({ csrf_token: getCsrfToken() })
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || `Server returned ${response.status}`);
                }

                const result = await response.json();
                showAlert(result.message || 'Doctor deleted successfully', 'success');
                await loadDoctorsForDepartment();

            } catch (error) {
                console.error('Error deleting doctor:', error);
                showAlert('Error deleting doctor: ' + error.message, 'danger');
            }
        }
    });
}

// Edit doctor function
async function editDoctor(doctorId) {
    const editDoctorModal = document.getElementById('editDoctorModal');
    if (!editDoctorModal) {
        console.error('Edit doctor modal not found');
        return;
    }

    try {
        const response = await fetch(`/api/doctors/${doctorId}/details`, {
            headers: {
                'X-CSRF-Token': getCsrfToken()
            }
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Doctor details not found (Status: ${response.status})`);
        }

        const doctor = await response.json();

        document.getElementById('editDoctorId').value = doctor.id;
        document.getElementById('editDoctorName').value = doctor.name;
        document.getElementById('editDoctorGender').value = doctor.gender;

        if (doctor.schedule_parts) {
            document.getElementById('editStartDay').value = doctor.schedule_parts.start_day || '';
            document.getElementById('editEndDay').value = doctor.schedule_parts.end_day || '';
            document.getElementById('editStartTime').value = doctor.schedule_parts.start_time || '';
            document.getElementById('editEndTime').value = doctor.schedule_parts.end_time || '';
        }

        editDoctorModal.style.display = 'block';
    } catch (error) {
        console.error('Error fetching doctor details:', error);
        showAlert(`Could not load doctor details: ${error.message}`, 'danger');
    }
}

// Save doctor changes
async function saveDoctorChanges() {
    const form = document.getElementById('editDoctorForm');
    if (!form) {
        console.error('Edit doctor form not found');
        return;
    }

    const formData = {
        doctor_id: form.querySelector('[name="doctor_id"]').value,
        name: form.querySelector('[name="name"]').value.trim(),
        gender: form.querySelector('[name="gender"]').value,
        start_day: form.querySelector('[name="start_day"]').value.toLowerCase(),
        end_day: form.querySelector('[name="end_day"]').value.toLowerCase(),
        start_time: form.querySelector('[name="start_time"]').value,
        end_time: form.querySelector('[name="end_time"]').value,
        csrf_token: getCsrfToken()
    };

    if (!formData.doctor_id || !formData.name || !formData.gender || !formData.start_day ||
        !formData.end_day || !formData.start_time || !formData.end_time || !formData.csrf_token) {
        showAlert('Please fill all required fields', 'danger');
        return;
    }

    try {
        const response = await fetch('/update_doctor', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': formData.csrf_token
            },
            body: JSON.stringify(formData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.message || 'Failed to update doctor');
        }

        const result = await response.json();
        if (result.success) {
            showAlert('Doctor updated successfully', 'success');
            document.getElementById('editDoctorModal').style.display = 'none';
            await loadDoctorsForDepartment();
        } else {
            throw new Error(result.message || 'Failed to update doctor');
        }
    } catch (error) {
        console.error('Error updating doctor:', error);
        showAlert('Error updating doctor: ' + error.message, 'danger');
    }
}

// Initialize booking form functionality
function initBookingForm() {
    const hospitalSelect = document.getElementById('hospital');
    const departmentSelect = document.getElementById('department');
    const doctorSelect = document.getElementById('doctor');
    const dateInput = document.getElementById('date');
    const timeSelect = document.getElementById('time');
    const loadingSpinner = document.getElementById('loadingSpinner');
    const slotAvailability = document.getElementById('slotAvailability');
    const submitBtn = document.getElementById('submitBtn');

    if (!hospitalSelect || !departmentSelect || !doctorSelect || !dateInput || !timeSelect ||
        !loadingSpinner || !slotAvailability || !submitBtn) {
        console.error('Booking form elements missing');
        return;
    }

    const today = new Date().toISOString().split('T')[0];
    dateInput.min = today;
    loadingSpinner.style.display = 'none';

    async function fetchAvailableSlots(doctorId, date, timeSelect, slotAvailability) {
        if (!date || !doctorId) {
            timeSelect.disabled = true;
            timeSelect.innerHTML = '<option value="" disabled selected>Select a doctor and date</option>';
            return;
        }

        loadingSpinner.style.display = 'block';
        timeSelect.disabled = true;
        timeSelect.innerHTML = '<option value="" disabled selected>Loading available slots...</option>';
        slotAvailability.textContent = '';
        slotAvailability.className = '';

        try {
            const response = await fetch(`/get_available_slots?doctor_id=${doctorId}&date=${date}`, {
                headers: {
                    'X-CSRF-Token': getCsrfToken()
                }
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `Failed to load slots: ${response.status}`);
            }

            const slots = await response.json();
            timeSelect.innerHTML = '<option value="" disabled selected>Select a time slot</option>';
            if (slots.length === 0) {
                slotAvailability.textContent = 'No available slots for this date';
                slotAvailability.className = 'slot-unavailable';
            } else {
                slotAvailability.textContent = 'Slots available';
                slotAvailability.className = 'slot-available';
                slots.forEach(slot => {
                    const option = document.createElement('option');
                    option.value = slot;
                    option.textContent = slot;
                    timeSelect.appendChild(option);
                });
                timeSelect.disabled = false;
            }
        } catch (error) {
            console.error('Error loading slots:', error);
            timeSelect.innerHTML = '<option value="" disabled selected>Error loading slots</option>';
            slotAvailability.textContent = 'Error loading available slots';
            slotAvailability.className = 'slot-unavailable';
            showAlert('Error loading slots: ' + error.message, 'danger');
        } finally {
            loadingSpinner.style.display = 'none';
        }
    }

    hospitalSelect.addEventListener('change', async function() {
        const hospitalId = this.value;
        departmentSelect.disabled = true;
        departmentSelect.innerHTML = '<option value="" disabled selected>Loading departments...</option>';
        doctorSelect.disabled = true;
        doctorSelect.innerHTML = '<option value="" disabled selected>Select a department first</option>';
        timeSelect.disabled = true;
        timeSelect.innerHTML = '<option value="" disabled selected>Select a doctor first</option>';

        if (!hospitalId) return;

        try {
            const response = await fetch(`/get_departments/${hospitalId}`, {
                headers: {
                    'X-CSRF-Token': getCsrfToken()
                }
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `Failed to load departments: ${response.status}`);
            }

            const departments = await response.json();
            departmentSelect.innerHTML = '<option value="" disabled selected>Select a department</option>';
            departments.forEach(dept => {
                const option = document.createElement('option');
                option.value = dept.id;
                option.textContent = dept.name;
                departmentSelect.appendChild(option);
            });
            departmentSelect.disabled = false;
        } catch (error) {
            console.error('Error loading departments:', error);
            departmentSelect.innerHTML = '<option value="" disabled selected>Error loading departments</option>';
            showAlert('Error loading departments: ' + error.message, 'danger');
        }
    });

    departmentSelect.addEventListener('change', async function() {
        const departmentId = this.value;
        doctorSelect.disabled = true;
        doctorSelect.innerHTML = '<option value="" disabled selected>Loading doctors...</option>';
        timeSelect.disabled = true;
        timeSelect.innerHTML = '<option value="" disabled selected>Select a doctor first</option>';

        if (!departmentId) return;

        try {
            const response = await fetch(`/get_doctors/${departmentId}`, {
                headers: {
                    'X-CSRF-Token': getCsrfToken()
                }
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `Failed to load doctors: ${response.status}`);
            }

            const doctors = await response.json();
            doctorSelect.innerHTML = '<option value="" disabled selected>Select a doctor</option>';
            doctors.forEach(doctor => {
                const option = document.createElement('option');
                option.value = doctor.id;
                option.textContent = doctor.name;
                doctorSelect.appendChild(option);
            });
            doctorSelect.disabled = false;
        } catch (error) {
            console.error('Error loading doctors:', error);
            doctorSelect.innerHTML = '<option value="" disabled selected>Error loading doctors</option>';
            showAlert('Error loading doctors: ' + error.message, 'danger');
        }
    });

    doctorSelect.addEventListener('change', function() {
        if (dateInput.value) {
            fetchAvailableSlots(this.value, dateInput.value, timeSelect, slotAvailability);
        }
    });

    dateInput.addEventListener('change', function() {
        if (doctorSelect.value) {
            fetchAvailableSlots(doctorSelect.value, this.value, timeSelect, slotAvailability);
        }
    });

    document.getElementById('bookingForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Booking...';

        try {
            const formData = {
                hospital: hospitalSelect.value,
                department: departmentSelect.value,
                doctor: doctorSelect.value,
                date: dateInput.value,
                time: timeSelect.value,
                health_challenge: document.getElementById('health_challenge').value.trim(),
                csrf_token: getCsrfToken()
            };

            if (!formData.hospital || !formData.department || !formData.doctor ||
                !formData.date || !formData.time || !formData.health_challenge || !formData.csrf_token) {
                throw new Error('Please fill all required fields');
            }

            const response = await fetch('/book', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': formData.csrf_token
                },
                body: JSON.stringify(formData)
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || `Booking failed: ${response.status}`);
            }

            const result = await response.json();
            if (result.success) {
                showAlert('Appointment booked successfully!', 'success');
                if (result.redirect) {
                    window.location.href = result.redirect;
                }
            } else {
                throw new Error(result.message || 'Booking failed');
            }
        } catch (error) {
            console.error('Booking error:', error);
            showAlert('Booking failed: ' + error.message, 'danger');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fas fa-calendar-check"></i> Book Appointment';
        }
    });
}

// Reschedule Appointment Modal
function setupRescheduleModal() {
    const modal = document.getElementById('rescheduleModal');
    const rescheduleButtons = document.querySelectorAll('.reschedule-btn');
    const closeBtn = document.querySelector('#rescheduleModal .close-modal');
    const cancelBtn = document.getElementById('cancelRescheduleBtn');
    const rescheduleForm = document.getElementById('rescheduleForm');
    const appointmentIdInput = document.getElementById('appointmentId');
    const doctorIdInput = document.getElementById('doctorId');
    const dateInput = document.getElementById('rescheduleDate');
    const timeSelect = document.getElementById('rescheduleTime');
    const scheduleDisplay = document.getElementById('doctorScheduleDisplay');
    const timeAvailability = document.getElementById('timeAvailability');

    if (!modal || !rescheduleForm || !dateInput || !timeSelect || !scheduleDisplay || !timeAvailability) {
        console.error('Reschedule modal elements missing');
        return;
    }

    const today = new Date().toISOString().split('T')[0];
    dateInput.setAttribute('min', today);

    async function fetchRescheduleSlots(doctorId, date) {
        if (!date || !doctorId) {
            timeSelect.disabled = true;
            timeSelect.innerHTML = '<option value="" disabled selected>Select a date</option>';
            return;
        }

        timeSelect.innerHTML = '<option value="" disabled selected>Loading slots...</option>';
        timeAvailability.textContent = 'Loading...';
        timeAvailability.className = 'availability-status';

        try {
            const response = await fetch(`/get_available_slots?doctor_id=${doctorId}&date=${date}`, {
                headers: {
                    'X-CSRF-Token': getCsrfToken()
                }
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP error: ${response.status}`);
            }
            const slots = await response.json();

            timeSelect.innerHTML = '<option value="" disabled selected>Select a time</option>';
            if (slots.length === 0) {
                timeAvailability.textContent = 'No available slots for this date';
                timeAvailability.className = 'availability-status unavailable';
            } else {
                slots.forEach(slot => {
                    const option = document.createElement('option');
                    option.value = slot;
                    option.textContent = slot;
                    timeSelect.appendChild(option);
                });
                timeAvailability.textContent = 'Available slots loaded';
                timeAvailability.className = 'availability-status available';
                timeSelect.disabled = false;
            }
        } catch (error) {
            console.error('Error fetching slots:', error);
            timeAvailability.textContent = 'Error loading slots';
            timeAvailability.className = 'availability-status error';
            showAlert('Error loading slots: ' + error.message, 'danger');
        }
    }

    rescheduleButtons.forEach(button => {
        button.addEventListener('click', function() {
            const apptId = this.getAttribute('data-appt-id');
            const doctorId = this.getAttribute('data-doctor-id');
            const doctorSchedule = this.getAttribute('data-doctor-schedule');

            if (!apptId || apptId === 'null' || !doctorId) {
                showAlert('Invalid appointment or doctor ID', 'danger');
                console.error('Invalid attributes:', { apptId, doctorId });
                return;
            }

            appointmentIdInput.value = apptId;
            doctorIdInput.value = doctorId;
            scheduleDisplay.textContent = formatSchedule(doctorSchedule) || 'Not available';
            dateInput.value = '';
            timeSelect.innerHTML = '<option value="" disabled selected>Select a time</option>';
            timeAvailability.textContent = '';
            timeAvailability.className = 'availability-status';

            modal.style.display = 'block';

            dateInput.removeEventListener('change', dateInput._changeHandler);
            dateInput._changeHandler = function() {
                fetchRescheduleSlots(doctorIdInput.value, this.value);
            };
            dateInput.addEventListener('change', dateInput._changeHandler);
        });
    });

    rescheduleForm.addEventListener('submit', async function(event) {
        event.preventDefault();
        const appointmentId = appointmentIdInput.value;
        const date = dateInput.value;
        const time = timeSelect.value;
        const isHospitalAdmin = rescheduleForm.getAttribute('data-is-hospital-admin') === 'true';

        if (!appointmentId || appointmentId === 'null' || !date || !time) {
            showAlert('Please select a valid appointment, date, and time', 'danger');
            return;
        }

        const selectedDate = new Date(date);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        if (selectedDate < today) {
            showAlert('Cannot reschedule to a past date', 'danger');
            return;
        }

        const endpoint = isHospitalAdmin ? '/reschedule_appointment' : `/reschedule_patient/${appointmentId}`;
        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': getCsrfToken()
                },
                body: JSON.stringify({ appointment_id: appointmentId, date, time, csrf_token: getCsrfToken() })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || `HTTP error: ${response.status}`);
            }
            const data = await response.json();

            if (data.success) {
                showAlert(data.message || 'Appointment rescheduled successfully', 'success');
                modal.style.display = 'none';
                setTimeout(() => window.location.reload(), 1000);
            } else {
                throw new Error(data.message || 'Failed to reschedule appointment');
            }
        } catch (error) {
            console.error('Error rescheduling:', error);
            showAlert('Error rescheduling appointment: ' + error.message, 'danger');
        }
    });

    function closeModal() {
        modal.style.display = 'none';
        dateInput.value = '';
        timeSelect.innerHTML = '<option value="" disabled selected>Select a time</option>';
        timeAvailability.textContent = '';
        timeAvailability.className = 'availability-status';
        scheduleDisplay.textContent = '';
        appointmentIdInput.value = '';
        doctorIdInput.value = '';
        dateInput.removeEventListener('change', dateInput._changeHandler);
    }

    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);

    window.addEventListener('click', function(event) {
        if (event.target === modal) {
            closeModal();
        }
    });
}

// Cancel Appointment
function setupCancelAppointment() {
    const cancelButtons = document.querySelectorAll('.cancel-appointment-btn');

    cancelButtons.forEach(button => {
        button.addEventListener('click', function() {
            const appointmentId = this.getAttribute('data-appt-id');
            if (!appointmentId) {
                showAlert('Invalid appointment ID', 'danger');
                return;
            }

            showConfirm('Are you sure you want to cancel this appointment?', async (confirmed) => {
                if (confirmed) {
                    try {
                        const response = await fetch(`/cancel_appointment/${appointmentId}`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRF-Token': getCsrfToken()
                            },
                            body: JSON.stringify({ csrf_token: getCsrfToken() })
                        });

                        if (!response.ok) {
                            const errorData = await response.json();
                            throw new Error(errorData.message || `HTTP error: ${response.status}`);
                        }

                        showAlert('Appointment cancelled successfully', 'success');
                        setTimeout(() => window.location.reload(), 1000);
                    } catch (error) {
                        console.error('Error cancelling appointment:', error);
                        showAlert('Error cancelling appointment: ' + error.message, 'danger');
                    }
                }
            });
        });
    });
}

// Debounce function for search
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Search functionality
function setupSearch() {
    const searchInputs = document.querySelectorAll('.search-input');
    const searchResults = document.querySelectorAll('.search-results');

    searchInputs.forEach((input, index) => {
        const resultsContainer = searchResults[index];
        const pageType = input.getAttribute('data-search-type');

        if (!pageType || !resultsContainer) {
            console.warn('Search input or results container missing or misconfigured:', { input, resultsContainer, pageType });
            return;
        }

        const performSearch = debounce(async function() {
            const query = input.value.trim();
            if (query.length < 2) {
                resultsContainer.innerHTML = '';
                return;
            }

            resultsContainer.innerHTML = '<div class="text-center">Loading...</div>';

            try {
                const response = await fetch(`/search_${pageType}?q=${encodeURIComponent(query)}`, {
                    headers: {
                        'X-CSRF-Token': getCsrfToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || `Search failed: ${response.status}`);
                }

                const results = await response.json();
                resultsContainer.innerHTML = '';

                if (results.length === 0) {
                    resultsContainer.innerHTML = '<div class="text-center">No results found</div>';
                    return;
                }

                results.forEach(item => {
                    const itemElement = document.createElement('div');
                    itemElement.className = 'search-result-item';
                    if (pageType === 'hospitals') {
                        itemElement.innerHTML = `
                            <div>${item.name}</div>
                            <div>${item.address || 'No address provided'}</div>
                        `;
                    } else if (pageType === 'doctors') {
                        itemElement.innerHTML = `
                            <div>${item.name}</div>
                            <div>${item.department_name || 'No department'}</div>
                            <div>${formatSchedule(item.schedule)}</div>
                        `;
                    } else if (pageType === 'appointments') {
                        itemElement.innerHTML = `
                            <div>Dr. ${item.doctor_name}</div>
                            <div>${item.date} at ${item.time}</div>
                            <div>Status: ${item.status}</div>
                            <button class="btn btn-sm btn-primary reschedule-btn"
                                    data-appt-id="${item.id}"
                                    data-doctor-id="${item.doctor_id}"
                                    data-doctor-schedule="${item.doctor_schedule}">
                                Reschedule
                            </button>
                        `;
                    }
                    resultsContainer.appendChild(itemElement);
                });

                if (pageType === 'appointments') {
                    setupRescheduleModal();
                }

            } catch (error) {
                console.error('Search error:', error);
                resultsContainer.innerHTML = '<div class="text-center error">Error loading results</div>';
                showAlert('Error performing search: ' + error.message, 'danger');
            }
        }, 300);

        input.addEventListener('input', performSearch);
    });
}

// Initialize all functionality
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM fully loaded');

    // Navbar toggle for mobile
    const navbarToggle = document.querySelector('.navbar-toggle');
    const navbarLinks = document.querySelector('.navbar-links');
    if (navbarToggle && navbarLinks) {
        navbarToggle.addEventListener('click', () => {
            navbarLinks.classList.toggle('active');
        });
    }

    // Profile toggle and update
    const toggleProfileBtn = document.getElementById('toggleProfileBtn');
    const profileForm = document.getElementById('profileForm');
    if (toggleProfileBtn && profileForm) {
        toggleProfileBtn.addEventListener('click', function() {
            profileForm.style.display = profileForm.style.display === 'none' ? 'block' : 'none';
        });
    }

    const updateProfileForm = document.getElementById('updateProfileForm');
    if (updateProfileForm) {
        updateProfileForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const submitBtn = this.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';

            try {
                const formData = new FormData(this);
                formData.append('csrf_token', getCsrfToken());

                const response = await fetch('/update_profile', {
                    method: 'POST',
                    headers: {
                        'X-CSRF-Token': getCsrfToken()
                    },
                    body: formData
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.message || 'Failed to update profile');
                }

                showAlert('Profile updated successfully', 'success');
                profileForm.style.display = 'none';
                setTimeout(() => window.location.reload(), 1000);
            } catch (error) {
                console.error('Error updating profile:', error);
                showAlert('Error updating profile: ' + error.message, 'danger');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = 'Save Profile';
            }
        });
    }

    // Initialize booking form
    if (document.getElementById('bookingForm')) {
        initBookingForm();
    }

    // Password toggle for login forms
    const togglePassword = document.querySelector('#togglePassword');
    const password = document.querySelector('#password');
    if (togglePassword && password) {
        togglePassword.addEventListener('click', function() {
            const type = password.getAttribute('type') === 'password' ? 'text' : 'password';
            password.setAttribute('type', type);
            this.classList.toggle('fa-eye');
            this.classList.toggle('fa-eye-slash');
        });
    }

    // Department selection and doctor management
    const departmentSelect = document.getElementById('departmentSelect');
    if (departmentSelect) {
        departmentSelect.addEventListener('change', loadDoctorsForDepartment);
        if (departmentSelect.value) {
            loadDoctorsForDepartment();
        }
    }

    // Add department modal
    const showAddDepartmentBtn = document.getElementById('showAddDepartmentBtn');
    const addDepartmentModal = document.getElementById('addDepartmentModal');
    const closeDepartmentModal = document.getElementById('closeDepartmentModal');
    const cancelAddDepartmentBtn = document.getElementById('cancelAddDepartmentBtn');

    if (showAddDepartmentBtn && addDepartmentModal) {
        showAddDepartmentBtn.addEventListener('click', () => addDepartmentModal.style.display = 'block');
    }
    if (closeDepartmentModal) {
        closeDepartmentModal.addEventListener('click', () => addDepartmentModal.style.display = 'none');
    }
    if (cancelAddDepartmentBtn) {
        cancelAddDepartmentBtn.addEventListener('click', () => addDepartmentModal.style.display = 'none');
    }

    // Add doctor card
    const showAddDoctorBtn = document.getElementById('showAddDoctorBtn');
    const addDoctorCard = document.getElementById('addDoctorCard');
    const cancelAddDoctorBtn = document.getElementById('cancelAddDoctorBtn');

    if (showAddDoctorBtn && addDoctorCard) {
        showAddDoctorBtn.addEventListener('click', function() {
            const deptId = document.getElementById('departmentSelect').value;
            if (!deptId) {
                showAlert('Please select a department first', 'warning');
                return;
            }
            document.querySelector('#addDoctorForm [name="department_id"]').value = deptId;
            addDoctorCard.style.display = 'block';
        });
    }
    if (cancelAddDoctorBtn) {
        cancelAddDoctorBtn.addEventListener('click', () => addDoctorCard.style.display = 'none');
    }

    // Add doctor form submission
    const addDoctorForm = document.getElementById('addDoctorForm');
    if (addDoctorForm) {
        addDoctorForm.addEventListener('submit', function(e) {
            e.preventDefault();
            addDoctor();
        });
    }

    // Edit doctor modal
    const editDoctorModal = document.getElementById('editDoctorModal');
    const closeEditDoctorModal = document.getElementById('closeEditDoctorModal');
    const cancelEditDoctorBtn = document.getElementById('cancelEditDoctorBtn');
    const editDoctorForm = document.getElementById('editDoctorForm');

    if (closeEditDoctorModal) {
        closeEditDoctorModal.addEventListener('click', () => editDoctorModal.style.display = 'none');
    }
    if (cancelEditDoctorBtn) {
        cancelEditDoctorBtn.addEventListener('click', () => editDoctorModal.style.display = 'none');
    }
    if (editDoctorForm) {
        editDoctorForm.addEventListener('submit', function(e) {
            e.preventDefault();
            saveDoctorChanges();
        });
    }

    window.addEventListener('click', (event) => {
        if (event.target === addDepartmentModal) addDepartmentModal.style.display = 'none';
        if (event.target === editDoctorModal) editDoctorModal.style.display = 'none';
    });

    // Delete hospital modal
    if (document.getElementById('deleteHospitalModal')) {
        setupHospitalDeletion();
    }

    // Reschedule modal
    if (document.getElementById('rescheduleModal')) {
        setupRescheduleModal();
    }

    // Cancel appointment
    if (document.querySelector('.cancel-appointment-btn')) {
        setupCancelAppointment();
    }

    // Search functionality
    const searchInputs = document.querySelectorAll('.search-input');
    if (searchInputs.length > 0) {
        setupSearch();
    }
});