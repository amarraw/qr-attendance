# attendance/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
import json
import csv
import pandas as pd
from io import BytesIO

from .models import Student, AttendanceSession, AttendanceRecord, QRCode, AdminProfile
from .forms import StudentRegistrationForm, AdminRegistrationForm, LoginForm, AttendanceSessionForm, QRScanForm
from .decorators import student_required, admin_required

def home(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'student_profile'):
            return redirect('student_dashboard')
        elif hasattr(request.user, 'admin_profile'):
            return redirect('admin_dashboard')
    return render(request, 'attendance/home.html')

def register_student(request):
    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Registration successful! Please login.')
            return redirect('login')
    else:
        form = StudentRegistrationForm()
    return render(request, 'attendance/register_student.html', {'form': form})

def register_admin(request):
    if request.method == 'POST':
        form = AdminRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Admin registration successful! Please login.')
            return redirect('login')
    else:
        form = AdminRegistrationForm()
    return render(request, 'attendance/register_admin.html', {'form': form})

def user_login(request):
    if request.user.is_authenticated:
        return redirect('home')
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome back, {user.get_full_name()}!')
                
                # Redirect based on user type
                if hasattr(user, 'student_profile'):
                    return redirect('student_dashboard')
                elif hasattr(user, 'admin_profile'):
                    return redirect('admin_dashboard')
                else:
                    return redirect('home')
    else:
        form = LoginForm()
    
    return render(request, 'attendance/login.html', {'form': form})

def user_logout(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')

@login_required
@student_required
def student_dashboard(request):
    student = request.user.student_profile
    active_sessions = AttendanceSession.objects.filter(is_active=True, end_time__gte=timezone.now())
    
    # Generate new QR code
    qr_code = student.generate_qr_code()
    
    context = {
        'student': student,
        'active_sessions': active_sessions,
        'qr_code': qr_code,
    }
    return render(request, 'attendance/student_dashboard.html', context)

@login_required
@student_required
def get_qr_code(request):
    """API endpoint to get fresh QR code data"""
    student = request.user.student_profile
    qr_code = student.generate_qr_code()
    
    return JsonResponse({
        'qr_data': qr_code.code,
        'expires_at': qr_code.expires_at.isoformat(),
        'time_remaining': (qr_code.expires_at - timezone.now()).total_seconds()
    })

@login_required
@student_required
def attendance_history(request):
    student = request.user.student_profile
    records = AttendanceRecord.objects.filter(student=student).order_by('-timestamp')
    
    context = {
        'records': records,
    }
    return render(request, 'attendance/attendance_history.html', context)

@login_required
@admin_required
def admin_dashboard(request):
    admin = request.user.admin_profile
    today = timezone.now().date()
    
    # Get today's sessions created by this admin
    today_sessions = AttendanceSession.objects.filter(
        created_by=request.user,
        start_time__date=today
    )
    
    # Get active sessions
    active_sessions = AttendanceSession.objects.filter(
        created_by=request.user,
        is_active=True,
        end_time__gte=timezone.now()
    )
    
    context = {
        'admin': admin,
        'today_sessions': today_sessions,
        'active_sessions': active_sessions,
    }
    return render(request, 'attendance/admin_dashboard.html', context)

@login_required
@admin_required
def create_session(request):
    if request.method == 'POST':
        form = AttendanceSessionForm(request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            session.created_by = request.user
            session.save()
            messages.success(request, 'Attendance session created successfully!')
            return redirect('admin_dashboard')
    else:
        form = AttendanceSessionForm()
    
    return render(request, 'attendance/create_session.html', {'form': form})

@login_required
@admin_required
def scan_qr(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id, created_by=request.user)
    
    if not session.is_live():
        messages.error(request, 'This session is not active or has ended.')
        return redirect('admin_dashboard')
    
    if request.method == 'POST':
        form = QRScanForm(request.POST)
        if form.is_valid():
            qr_data = form.cleaned_data['qr_data']
            
            # Parse QR data
            try:
                if qr_data.startswith('ATT:'):
                    parts = qr_data.split(':')
                    if len(parts) >= 3:
                        student_id = parts[1]
                        token = parts[2]
                        
                        # Find student and valid QR code
                        student = get_object_or_404(Student, student_id=student_id)
                        qr_code = QRCode.objects.filter(
                            student=student,
                            token=token,
                            is_used=False,
                            expires_at__gte=timezone.now()
                        ).first()
                        
                        if qr_code:
                            # Check if already marked
                            existing_record = AttendanceRecord.objects.filter(
                                student=student,
                                session=session
                            ).first()
                            
                            if existing_record:
                                messages.warning(request, f'{student.user.get_full_name()} is already marked present!')
                            else:
                                # Create attendance record
                                AttendanceRecord.objects.create(
                                    student=student,
                                    session=session,
                                    qr_code=qr_code,
                                    ip_address=request.META.get('REMOTE_ADDR'),
                                    device_info=request.META.get('HTTP_USER_AGENT', '')
                                )
                                
                                # Mark QR as used
                                qr_code.is_used = True
                                qr_code.save()
                                
                                messages.success(request, f'Attendance marked for {student.user.get_full_name()}!')
                        else:
                            messages.error(request, 'Invalid or expired QR code!')
                    else:
                        messages.error(request, 'Invalid QR code format!')
                else:
                    messages.error(request, 'Invalid QR code!')
            except Exception as e:
                messages.error(request, f'Error processing QR code: {str(e)}')
    
    form = QRScanForm(initial={'session_id': session_id})
    
    # Get attendance count for this session
    attendance_count = AttendanceRecord.objects.filter(session=session).count()
    
    context = {
        'session': session,
        'form': form,
        'attendance_count': attendance_count,
    }
    return render(request, 'attendance/scan_qr.html', context)

@login_required
@admin_required
def view_session_attendance(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id, created_by=request.user)
    records = AttendanceRecord.objects.filter(session=session).select_related('student', 'student__user')
    
    context = {
        'session': session,
        'records': records,
    }
    return render(request, 'attendance/view_attendance.html', context)

@login_required
@admin_required
def export_attendance_csv(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id, created_by=request.user)
    records = AttendanceRecord.objects.filter(session=session).select_related('student', 'student__user')
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="attendance_{session.course_code}_{session.id}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Student ID', 'Name', 'Department', 'Year', 'Timestamp', 'IP Address'])
    
    for record in records:
        writer.writerow([
            record.student.student_id,
            record.student.user.get_full_name(),
            record.student.department,
            record.student.year,
            record.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            record.ip_address or 'N/A'
        ])
    
    return response

@login_required
@admin_required
def export_attendance_excel(request, session_id):
    session = get_object_or_404(AttendanceSession, id=session_id, created_by=request.user)
    records = AttendanceRecord.objects.filter(session=session).select_related('student', 'student__user')
    
    # Create DataFrame
    data = []
    for record in records:
        data.append({
            'Student ID': record.student.student_id,
            'Name': record.student.user.get_full_name(),
            'Department': record.student.department,
            'Year': record.student.year,
            'Timestamp': record.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'IP Address': record.ip_address or 'N/A',
            'Device Info': record.device_info
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Attendance', index=False)
    
    output.seek(0)
    
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="attendance_{session.course_code}_{session.id}.xlsx"'
    
    return response

@login_required
@admin_required
def manage_students(request):
    students = Student.objects.all().select_related('user')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        students = students.filter(
            models.Q(student_id__icontains=search_query) |
            models.Q(user__first_name__icontains=search_query) |
            models.Q(user__last_name__icontains=search_query) |
            models.Q(department__icontains=search_query)
        )
    
    context = {
        'students': students,
        'search_query': search_query,
    }
    return render(request, 'attendance/manage_students.html', context)

# API endpoint for QR scanning (for mobile/webcam)
@csrf_exempt
@login_required
@admin_required
def api_scan_qr(request, session_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            qr_data = data.get('qr_data')
            
            session = get_object_or_404(AttendanceSession, id=session_id, created_by=request.user)
            
            if not session.is_live():
                return JsonResponse({'success': False, 'message': 'Session is not active'})
            
            # Parse QR data
            if qr_data.startswith('ATT:'):
                parts = qr_data.split(':')
                if len(parts) >= 3:
                    student_id = parts[1]
                    token = parts[2]
                    
                    student = get_object_or_404(Student, student_id=student_id)
                    qr_code = QRCode.objects.filter(
                        student=student,
                        token=token,
                        is_used=False,
                        expires_at__gte=timezone.now()
                    ).first()
                    
                    if qr_code:
                        # Check if already marked
                        existing_record = AttendanceRecord.objects.filter(
                            student=student,
                            session=session
                        ).first()
                        
                        if existing_record:
                            return JsonResponse({
                                'success': False,
                                'message': f'{student.user.get_full_name()} is already marked present!'
                            })
                        
                        # Create attendance record
                        AttendanceRecord.objects.create(
                            student=student,
                            session=session,
                            qr_code=qr_code,
                            ip_address=request.META.get('REMOTE_ADDR'),
                            device_info=request.META.get('HTTP_USER_AGENT', '')
                        )
                        
                        # Mark QR as used
                        qr_code.is_used = True
                        qr_code.save()
                        
                        return JsonResponse({
                            'success': True,
                            'message': f'Attendance marked for {student.user.get_full_name()}!',
                            'student': {
                                'id': student.student_id,
                                'name': student.user.get_full_name(),
                                'department': student.department
                            }
                        })
            
            return JsonResponse({'success': False, 'message': 'Invalid or expired QR code'})
            
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Invalid JSON data'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})