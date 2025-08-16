document.addEventListener('DOMContentLoaded', function () {
    // Department and Doctor Management Functions
    const showAddDepartmentBtn = document.getElementById('showAddDepartmentBtn');
    const addDepartmentModal = document.getElementById('addDepartmentModal');
    const closeDepartmentModal = document.getElementById('closeDepartmentModal');
    const cancelAddDepartmentBtn = document.getElementById('cancelAddDepartmentBtn');
    const departmentSelectManage = document.getElementById('departmentSelect');
    const doctorManagementSection = document.getElementById('doctorManagementSection');
    const showAddDoctorBtn = document.getElementById('showAddDoctorBtn');
    const addDoctorCard = document.getElementById('addDoctorCard');
    const cancelAddDoctorBtn = document.getElementById('cancelAddDoctorBtn');
    const editDoctorModal = document.getElementById('editDoctorModal');
    const closeEditDoctorModal = document.getElementById('closeEditDoctorModal');
    const cancelEditDoctorBtn = document.getElementById('cancelEditDoctorBtn');

    if (showAddDepartmentBtn) {
        showAddDepartmentBtn.addEventListener('click', function() {
            addDepartmentModal.style.display = 'block';
        });
    }

    if (closeDepartmentModal) {
        closeDepartmentModal.addEventListener('click', function() {
            addDepartmentModal.style.display = 'none';
        });
    }

    if (cancelAddDepartmentBtn) {
        cancelAddDepartmentBtn.addEventListener('click', function() {
            addDepartmentModal.style.display = 'none';
        });
    }

    if (departmentSelectManage) {
        departmentSelectManage.addEventListener('change', loadDoctorsForDepartment);
    }

    if (showAddDoctorBtn) {
        showAddDoctorBtn.addEventListener('click', function() {
            addDoctorCard.style.display = 'block';
        });
    }

    if (cancelAddDoctorBtn) {
        cancelAddDoctorBtn.addEventListener('click', function() {
            addDoctorCard.style.display = 'none';
        });
    }

    if (closeEditDoctorModal) {
        closeEditDoctorModal.addEventListener('click', function() {
            editDoctorModal.style.display = 'none';
        });
    }

    if (cancelEditDoctorBtn) {
        cancelEditDoctorBtn.addEventListener('click', function() {
            editDoctorModal.style.display = 'none';
        });
    }

    function formatSchedule(schedule) {
        if (!schedule) return 'Not set';
        
        try {
            // Convert "mon-fri 9-17" to "Monday-Friday, 9:00 AM - 5:00 PM"
            const parts = schedule.toLowerCase().split(' ');
            if (parts.length !== 2) return schedule;
            
            const days = parts[0].split('-');
            const times = parts[1].split('-');
            
            if (days.length !== 2 || times.length !== 2) return schedule;
            
            const dayMap = {
                'mon': 'Monday',
                'tue': 'Tuesday',
                'wed': 'Wednesday',
                'thu': 'Thursday',
                'fri': 'Friday',
                'sat': 'Saturday',
                'sun': 'Sunday'
            };
            
            const startDay = dayMap[days[0]] || days[0];
            const endDay = dayMap[days[1]] || days[1];
            
            // Format times
            const formatTime = (timeStr) => {
                if (!timeStr) return '';
                const timeMatch = timeStr.match(/^(\d{1,2})(?::(\d{2}))?$/);
                if (!timeMatch) return timeStr;
                
                let hour = parseInt(timeMatch[1]);
                const minute = timeMatch[2] ? parseInt(timeMatch[2]) : 0;
                const period = hour >= 12 ? 'PM' : 'AM';
                hour = hour % 12 || 12;
                
                return `${hour}:${minute.toString().padStart(2, '0')} ${period}`;
            };
            
            const startTime = formatTime(times[0]);
            const endTime = formatTime(times[1]);
            
            return `${startDay}-${endDay}, ${startTime} - ${endTime}`;
        } catch (e) {
            console.error('Error formatting schedule:', e);
            return schedule;
        }
    }

    // Alert Fading
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.classList.add('fade');
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });

    // Close modals when clicking outside
    window.onclick = function(event) {
        if (event.target === addDepartmentModal) {
            addDepartmentModal.style.display = 'none';
        }
        if (event.target === editDoctorModal) {
            editDoctorModal.style.display = 'none';
        }
    }
});

// Global functions
function showAlert(message, type) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.textContent = message;
    document.body.insertBefore(alertDiv, document.body.firstChild);
    
    setTimeout(() => {
        alertDiv.classList.add('fade');
        setTimeout(() => alertDiv.remove(), 500);
    }, 5000);
}

async function editDoctor(doctorId) {
    try {
        const response = await fetch(`/get_doctor_details/${doctorId}`);
        if (!response.ok) throw new Error('Failed to fetch doctor details');
        const doctor = await response.json();
        
        // Populate the edit form
        document.getElementById('editDoctorId').value = doctor.id;
        document.getElementById('editDoctorName').value = doctor.name;
        document.getElementById('editDoctorGender').value = doctor.gender;
        
        // Parse schedule if available
        if (doctor.schedule_parts) {
            const parts = doctor.schedule_parts;
            document.getElementById('editStartDay').value = parts.start_day;
            document.getElementById('editEndDay').value = parts.end_day;
            
            // Set start time
            const startTimeSelect = document.getElementById('editStartTime');
            const startTimeOptions = Array.from(startTimeSelect.options);
            const startTimeMatch = startTimeOptions.find(opt => 
                opt.value.includes(parts.start_time.split(':')[0]));
            if (startTimeMatch) startTimeMatch.selected = true;
            
            // Set end time
            const endTimeSelect = document.getElementById('editEndTime');
            const endTimeOptions = Array.from(endTimeSelect.options);
            const endTimeMatch = endTimeOptions.find(opt => 
                opt.value.includes(parts.end_time.split(':')[0]));
            if (endTimeMatch) endTimeMatch.selected = true;
        }
        
        // Show the modal
        document.getElementById('editDoctorModal').style.display = 'block';
    } catch (error) {
        console.error('Error fetching doctor details:', error);
        showAlert('Error loading doctor details', 'danger');
    }
}

// Update saveDoctorChanges to handle notifications properly
async function saveDoctorChanges() {
    const form = document.getElementById('editDoctorForm');
    const formData = new FormData(form);
    
    try {
        const response = await fetch('/update_doctor', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.message || 'Failed to update doctor');
        }
        
        if (result.success) {
            // Only show one success notification
            showAlert('Doctor updated successfully', 'success');
            document.getElementById('editDoctorModal').style.display = 'none';
            
            // Reload the doctors list
            const departmentSelect = document.getElementById('departmentSelect');
            if (departmentSelect && departmentSelect.value) {
                await loadDoctorsForDepartment();
            }
        } else {
            throw new Error(result.message || 'Failed to update doctor');
        }
    } catch (error) {
        console.error('Error updating doctor:', error);
        // Only show one error notification
        showAlert('Error updating doctor: ' + error.message, 'danger');
    }
}


async function loadDoctorsForDepartment() {
    const deptId = document.getElementById('departmentSelect').value;
    const doctorManagementSection = document.getElementById('doctorManagementSection');
    const addDoctorDeptId = document.getElementById('addDoctorDeptId');
    
    if (!deptId) {
        doctorManagementSection.style.display = 'none';
        return;
    }
    
    addDoctorDeptId.value = deptId;
    doctorManagementSection.style.display = 'block';
    
    try {
        const response = await fetch(`/get_doctors/${deptId}`);
        if (!response.ok) throw new Error('Failed to fetch doctors');
        const doctors = await response.json();
        const doctorList = document.getElementById('doctorList');
        doctorList.innerHTML = '';
        
        if (doctors.length === 0) {
            doctorList.innerHTML = `
                <tr>
                    <td colspan="4" class="text-center">No doctors found in this department</td>
                </tr>
            `;
            return;
        }
        
        doctors.forEach(doc => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${doc.name}</td>
                <td>${doc.gender === 'M' ? 'Male' : 'Female'}</td>
                <td>${formatSchedule(doc.schedule)}</td>
                <td class="actions">
                    <button class="btn btn-sm btn-warning" onclick="editDoctor(${doc.id})">
                        <i class="fas fa-edit"></i> Edit
                    </button>
                    <form method="POST" action="/manage_departments" onsubmit="return confirm('Are you sure you want to delete this doctor?')">
                        <input type="hidden" name="doctor_id" value="${doc.id}">
                        <button type="submit" name="delete_doctor" class="btn btn-sm btn-danger">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    </form>
                </td>
            `;
            doctorList.appendChild(row);
        });
    } catch (error) {
        console.error('Error loading doctors:', error);
        const doctorList = document.getElementById('doctorList');
        doctorList.innerHTML = `
            <tr>
                <td colspan="4" class="text-center error">Error loading doctors</td>
            </tr>
        `;
        showAlert('Error loading doctors', 'danger');
    }
}

