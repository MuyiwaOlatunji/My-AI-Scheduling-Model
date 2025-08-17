// Global helper function to format schedule
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

// Load doctors for selected department
async function loadDoctorsForDepartment() {
    const deptId = document.getElementById('departmentSelect').value;
    const doctorManagementSection = document.getElementById('doctorManagementSection');
    const doctorList = document.getElementById('doctorList');
    
    if (!deptId) {
        doctorManagementSection.style.display = 'none';
        return;
    }
    
    try {
        doctorManagementSection.style.display = 'block';
        doctorList.innerHTML = '<tr><td colspan="4" class="text-center">Loading doctors...</td></tr>';
        
        const response = await fetch(`/api/departments/${deptId}/doctors`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        
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
                <td>${doc.gender === 'M' ? 'Male' : 'Female'}</td>
                <td>${formatSchedule(doc.schedule)}</td>
                <td class="actions">
                    <button class="btn btn-sm btn-warning" onclick="editDoctor(${doc.id})">
                        <i class="fas fa-edit"></i> Edit
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="confirmDeleteDoctor(${doc.id}, '${doc.name}')">
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
    const formData = {
        department_id: form.querySelector('[name="department_id"]').value,
        name: form.querySelector('[name="name"]').value,
        gender: form.querySelector('[name="gender"]').value,
        start_day: form.querySelector('[name="start_day"]').value,
        end_day: form.querySelector('[name="end_day"]').value,
        start_time: form.querySelector('[name="start_time"]').value,
        end_time: form.querySelector('[name="end_time"]').value
    };

    // Simple validation
    if (!formData.name || !formData.gender || !formData.start_day || !formData.end_day || 
        !formData.start_time || !formData.end_time) {
        showAlert('Please fill all required fields', 'danger');
        return;
    }

    try {
        const response = await fetch('/add_doctor', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
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
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    credentials: 'same-origin'
                });
                
                if (!response.ok) {
                    const errorData = await response.json().catch(() => null);
                    throw new Error(errorData?.error || `Server returned ${response.status}`);
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
    try {
        const response = await fetch(`/api/doctors/${doctorId}/details`);
        if (!response.ok) {
            throw new Error(`Doctor details not found (Status: ${response.status})`);
        }
        
        const doctor = await response.json();
        
        document.getElementById('editDoctorId').value = doctor.id;
        document.getElementById('editDoctorName').value = doctor.name;
        document.getElementById('editDoctorGender').value = doctor.gender;
        
        if (doctor.schedule) {
            const parts = doctor.schedule.toLowerCase().split(' ');
            if (parts.length === 2) {
                const days = parts[0].split('-');
                const times = parts[1].split('-');
                
                if (days.length === 2) {
                    document.getElementById('editStartDay').value = days[0];
                    document.getElementById('editEndDay').value = days[1];
                }
                
                if (times.length === 2) {
                    document.getElementById('editStartTime').value = times[0];
                    document.getElementById('editEndTime').value = times[1];
                }
            }
        }
        
        document.getElementById('editDoctorModal').style.display = 'block';
    } catch (error) {
        console.error('Error fetching doctor details:', error);
        showAlert(`Could not load doctor details: ${error.message}`, 'danger');
    }
}

// Save doctor changes
async function saveDoctorChanges() {
    const form = document.getElementById('editDoctorForm');
    const formData = {
        doctor_id: form.querySelector('[name="doctor_id"]').value,
        name: form.querySelector('[name="name"]').value,
        gender: form.querySelector('[name="gender"]').value,
        start_day: form.querySelector('[name="start_day"]').value,
        end_day: form.querySelector('[name="end_day"]').value,
        start_time: form.querySelector('[name="start_time"]').value,
        end_time: form.querySelector('[name="end_time"]').value
    };

    try {
        const response = await fetch('/update_doctor', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
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

// Initialize reschedule modal functionality
document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('rescheduleModal');
    const closeBtn = document.querySelector('.close-modal');
    const rescheduleBtns = document.querySelectorAll('.reschedule-btn');
    
    // Open modal when reschedule button is clicked
    rescheduleBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const apptId = this.getAttribute('data-appt-id');
            const doctorId = this.getAttribute('data-doctor-id');
            const doctorSchedule = this.getAttribute('data-doctor-schedule');
            
            document.getElementById('appointmentId').value = apptId;
            document.getElementById('doctorId').value = doctorId;
            document.getElementById('doctorScheduleDisplay').textContent = doctorSchedule;
            
            // Set minimum date to today
            const today = new Date().toISOString().split('T')[0];
            document.getElementById('rescheduleDate').min = today;
            
            modal.style.display = 'block';
        });
    });
    
    // Close modal
    closeBtn.addEventListener('click', function() {
        modal.style.display = 'none';
    });
    
    // Close when clicking outside modal
    window.addEventListener('click', function(event) {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    // Handle date change for time slots
    document.getElementById('rescheduleDate').addEventListener('change', async function() {
        const date = this.value;
        const doctorId = document.getElementById('doctorId').value;
        const timeSelect = document.getElementById('rescheduleTime');
        const availabilityStatus = document.getElementById('timeAvailability');
        
        if (!date || !doctorId) return;
        
        timeSelect.disabled = true;
        timeSelect.innerHTML = '<option value="" disabled selected>Loading available slots...</option>';
        availabilityStatus.textContent = '';
        
        try {
            const response = await fetch(`/get_available_slots?doctor_id=${doctorId}&date=${date}`);
            if (!response.ok) throw new Error('Failed to load available slots');
            
            const slots = await response.json();
            
            timeSelect.innerHTML = '<option value="" disabled selected>Select a time slot</option>';
            if (slots.length === 0) {
                availabilityStatus.textContent = 'No available slots for this date';
                availabilityStatus.className = 'availability-status unavailable';
            } else {
                availabilityStatus.textContent = '';
                slots.forEach(slot => {
                    const option = document.createElement('option');
                    option.value = slot;
                    option.textContent = slot;
                    timeSelect.appendChild(option);
                });
                timeSelect.disabled = false;
                availabilityStatus.className = 'availability-status available';
            }
        } catch (error) {
            console.error('Error loading slots:', error);
            timeSelect.innerHTML = '<option value="" disabled selected>Error loading slots</option>';
            availabilityStatus.textContent = 'Error loading available slots';
            availabilityStatus.className = 'availability-status error';
        }
    });
    
    // Handle form submission
    document.getElementById('rescheduleForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const formData = {
            appointment_id: document.getElementById('appointmentId').value,
            date: document.getElementById('rescheduleDate').value,
            time: document.getElementById('rescheduleTime').value
        };
        
        try {
            const response = await fetch('/reschedule_appointment', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.message || 'Rescheduling failed');
            }
            
            const result = await response.json();
            if (result.success) {
                alert('Appointment rescheduled successfully!');
                window.location.reload();
            } else {
                throw new Error(result.message || 'Rescheduling failed');
            }
        } catch (error) {
            console.error('Rescheduling error:', error);
            alert('Error rescheduling appointment: ' + error.message);
        }
    });
});

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
    
    // Set minimum date to today
    const today = new Date().toISOString().split('T')[0];
    dateInput.min = today;
    
    // Hide loading spinner initially
    loadingSpinner.style.display = 'none';

    // Hospital change event
    hospitalSelect.addEventListener('change', async function() {
        const hospitalId = this.value;
        if (!hospitalId) return;
        
        departmentSelect.disabled = true;
        departmentSelect.innerHTML = '<option value="" disabled selected>Loading departments...</option>';
        
        try {
            const response = await fetch(`/get_departments/${hospitalId}`);
            if (!response.ok) {
                const error = await response.text();
                throw new Error(`Failed to load departments: ${error}`);
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
            doctorSelect.disabled = true;
            doctorSelect.innerHTML = '<option value="" disabled selected>Select a department first</option>';
            timeSelect.disabled = true;
            timeSelect.innerHTML = '<option value="" disabled selected>Select a doctor first</option>';
        } catch (error) {
            console.error('Error loading departments:', error);
            departmentSelect.innerHTML = '<option value="" disabled selected>Error loading departments</option>';
            showAlert('Error loading departments: ' + error.message, 'danger');
        }
    });
    
    // Department change event
    departmentSelect.addEventListener('change', async function() {
        const departmentId = this.value;
        if (!departmentId) return;
        
        doctorSelect.disabled = true;
        doctorSelect.innerHTML = '<option value="" disabled selected>Loading doctors...</option>';
        
        try {
            const response = await fetch(`/get_doctors/${departmentId}`);
            if (!response.ok) {
                const error = await response.text();
                throw new Error(`Failed to load doctors: ${error}`);
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
            timeSelect.disabled = true;
            timeSelect.innerHTML = '<option value="" disabled selected>Select a date first</option>';
        } catch (error) {
            console.error('Error loading doctors:', error);
            doctorSelect.innerHTML = '<option value="" disabled selected>Error loading doctors</option>';
            showAlert('Error loading doctors: ' + error.message, 'danger');
        }
    });
    
    // Date change event
    dateInput.addEventListener('change', async function() {
        const date = this.value;
        const doctorId = doctorSelect.value;
        
        if (!date || !doctorId) {
            timeSelect.disabled = true;
            return;
        }
        
        loadingSpinner.style.display = 'block';
        timeSelect.disabled = true;
        timeSelect.innerHTML = '<option value="" disabled selected>Loading available slots...</option>';
        slotAvailability.textContent = '';
        slotAvailability.className = '';
        
        try {
            const response = await fetch(`/get_available_slots?doctor_id=${doctorId}&date=${date}`);
            if (!response.ok) {
                const error = await response.text();
                throw new Error(`Failed to load slots: ${error}`);
            }
            
            const slots = await response.json();
            
            timeSelect.innerHTML = '<option value="" disabled selected>Select a time slot</option>';
            if (slots.length === 0) {
                slotAvailability.textContent = 'No available slots for this date';
                slotAvailability.className = 'slot-unavailable';
            } else {
                slotAvailability.textContent = '';
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
    });
    
    // Form submission
    document.getElementById('bookingForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Booking...';
        
        try {
            // Create form data
            const formData = {
                hospital: hospitalSelect.value,
                department: departmentSelect.value,
                doctor: doctorSelect.value,
                date: dateInput.value,
                time: timeSelect.value,
                health_challenge: document.getElementById('health_challenge').value
            };

            // Validate form
            if (!formData.hospital || !formData.department || !formData.doctor || 
                !formData.date || !formData.time || !formData.health_challenge) {
                throw new Error('Please fill all required fields');
            }

            const response = await fetch('/book', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });

            if (!response.ok) {
                // Try to parse error as JSON, fall back to text if not JSON
                let error;
                try {
                    error = await response.json();
                } catch {
                    error = { message: await response.text() };
                }
                throw new Error(error.message || 'Booking failed');
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

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Department selection change
    const departmentSelect = document.getElementById('departmentSelect');
    if (departmentSelect) {
        departmentSelect.addEventListener('change', loadDoctorsForDepartment);
        if (departmentSelect.value) {
            loadDoctorsForDepartment();
        }
    }

    // Modal and card toggles
    const showAddDepartmentBtn = document.getElementById('showAddDepartmentBtn');
    const addDepartmentModal = document.getElementById('addDepartmentModal');
    const closeDepartmentModal = document.getElementById('closeDepartmentModal');
    const cancelAddDepartmentBtn = document.getElementById('cancelAddDepartmentBtn');

    if (showAddDepartmentBtn) {
        showAddDepartmentBtn.addEventListener('click', () => addDepartmentModal.style.display = 'block');
    }
    if (closeDepartmentModal) {
        closeDepartmentModal.addEventListener('click', () => addDepartmentModal.style.display = 'none');
    }
    if (cancelAddDepartmentBtn) {
        cancelAddDepartmentBtn.addEventListener('click', () => addDepartmentModal.style.display = 'none');
    }

    const showAddDoctorBtn = document.getElementById('showAddDoctorBtn');
    const addDoctorCard = document.getElementById('addDoctorCard');
    const cancelAddDoctorBtn = document.getElementById('cancelAddDoctorBtn');

    if (showAddDoctorBtn) {
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

    const editDoctorModal = document.getElementById('editDoctorModal');
    const closeEditDoctorModal = document.getElementById('closeEditDoctorModal');
    const cancelEditDoctorBtn = document.getElementById('cancelEditDoctorBtn');

    if (closeEditDoctorModal) {
        closeEditDoctorModal.addEventListener('click', () => editDoctorModal.style.display = 'none');
    }
    if (cancelEditDoctorBtn) {
        cancelEditDoctorBtn.addEventListener('click', () => editDoctorModal.style.display = 'none');
    }

    // Close modals when clicking outside
    window.addEventListener('click', (event) => {
        if (event.target === addDepartmentModal) addDepartmentModal.style.display = 'none';
        if (event.target === editDoctorModal) editDoctorModal.style.display = 'none';
    });

    // Initialize booking form if on booking page
    if (document.getElementById('bookingForm')) {
        initBookingForm();
    }

    // Add event listener for doctor form submission
    const addDoctorForm = document.getElementById('addDoctorForm');
    if (addDoctorForm) {
        addDoctorForm.addEventListener('submit', function(e) {
            e.preventDefault();
            addDoctor();
        });
    }
});