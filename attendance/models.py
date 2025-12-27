# attendance/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid
import qrcode
from io import BytesIO
from django.core.files import File
from PIL import Image, ImageDraw
import hashlib
import time as t
from django.utils.timezone import now       

class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    student_id = models.CharField(max_length=20, unique=True)
    department = models.CharField(max_length=100)
    year = models.IntegerField(default=1)
    phone = models.CharField(max_length=15, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.student_id} - {self.user.get_full_name()}"
    
    def generate_qr_code(self):
        # Generate unique token
        token = hashlib.sha256(f"{self.student_id}{t.time()}".encode()).hexdigest()[:10]
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        data = f"ATT:{self.student_id}:{token}"
        qr.add_data(data)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to BytesIO
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        
        # Save to file
        filename = f'qr_{self.student_id}_{token}.png'
        
        # Create or update QR code record
        qr_code_obj, created = QRCode.objects.get_or_create(student=self)
        qr_code_obj.code = data
        qr_code_obj.token = token
        qr_code_obj.expires_at = timezone.now() + timezone.timedelta(seconds=30)
        qr_code_obj.save()
        
        return qr_code_obj
    
    def save(self, *args, **kwargs):
        if not self.student_id:
            year = now().year
            last_student = Student.objects.filter(
                student_id__startswith=f"STU{year}"
            ).order_by('-student_id').first()
            if last_student:
                last_number = int(last_student.student_id[-4:])
                new_number = last_number + 1
            else:
                new_number = 1
            self.student_id = f"STU{year}{new_number:04d}"

        super().save(*args, **kwargs)

class QRCode(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='qr_codes')
    code = models.TextField()
    token = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at
    
    def __str__(self):
        return f"QR for {self.student.student_id} - Valid: {self.is_valid()}"

class AttendanceSession(models.Model):
    SESSION_TYPES = [
        ('lecture', 'Lecture'),
        ('lab', 'Lab'),
        ('tutorial', 'Tutorial'),
        ('exam', 'Exam'),
    ]
    
    name = models.CharField(max_length=200)
    course_code = models.CharField(max_length=20)
    session_type = models.CharField(max_length=20, choices=SESSION_TYPES, default='lecture')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    location = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.course_code} - {self.name}"
    
    def is_live(self):
        now = timezone.now()
        return self.is_active and self.start_time <= now <= self.end_time

class AttendanceRecord(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='records')
    qr_code = models.ForeignKey(QRCode, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_info = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['student', 'session']  # Prevent duplicate attendance
    
    def __str__(self):
        return f"{self.student.student_id} - {self.session.name}"

class AdminProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    department = models.CharField(max_length=100)
    can_create_sessions = models.BooleanField(default=True)
    can_export_data = models.BooleanField(default=True)
    can_manage_students = models.BooleanField(default=True)
    
    def __str__(self):
        return f"Admin: {self.user.get_full_name()}"