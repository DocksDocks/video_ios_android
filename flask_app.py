import os
import zipfile
from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import shutil
import ffmpeg
import string
import random


app = Flask(__name__)

scheduler = BackgroundScheduler()

# Configure upload folder and allowed extensions
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configure output folder for converted files
OUTPUT_FOLDER = 'converted'
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

# Configure temporary folder for storing uploaded files
TEMP_FOLDER = 'temp'
app.config['TEMP_FOLDER'] = TEMP_FOLDER

# Configure Flask to use tailwind CSS
app.static_folder = 'static'

def generate_random_string(length):
    letters = string.ascii_lowercase + string.ascii_uppercase
    return ''.join(random.choice(letters) for _ in range(length))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def delete_files(zip_filepath):
    temp_folder = app.config['TEMP_FOLDER']
    converted_folder = app.config['OUTPUT_FOLDER']
    current_time = datetime.now()

    # Delete temporary files
    for filename in os.listdir(temp_folder):
        file_path = os.path.join(temp_folder, filename)
        modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        if current_time - modified_time > timedelta(minutes=1):
            os.remove(file_path)

    # Delete converted files
    for filename in os.listdir(converted_folder):
        file_path = os.path.join(converted_folder, filename)
        modified_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        if current_time - modified_time > timedelta(minutes=1):
            os.remove(file_path)

    # Delete the generated zip file
    if current_time - modified_time > timedelta(minutes=1) and os.path.exists(zip_filepath):
        os.remove(zip_filepath)

def get_scaled_resolution(input_path, target_height):
    probe = ffmpeg.probe(input_path)
    video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
    if video_stream:
        width = int(video_stream['width'])
        height = int(video_stream['height'])
        target_width = int(target_height * width / height)
        return f"{target_width}x{target_height}"
    return None

def convert_video_to_h264(input_path, output_path, resolution):
    output_filename = os.path.splitext(os.path.basename(input_path))[0] + '.mp4'
    output_filepath = os.path.join(output_path, output_filename)
    ffmpeg.input(input_path).output(output_filepath, vcodec='libx264', preset='medium', s=resolution, an=None).run(overwrite_output=True)
    return output_filepath

def convert_video_to_vp8(input_path, output_path, resolution):
    output_filename = os.path.splitext(os.path.basename(input_path))[0] + '.webm'
    output_filepath = os.path.join(output_path, output_filename)
    ffmpeg.input(input_path).output(output_filepath, vcodec='libvpx', s=resolution, an=None).run(overwrite_output=True)
    return output_filepath


@app.route('/', methods=['GET', 'POST'])
def landing_page():
    if request.method == 'POST':
        # Check if files were uploaded
        if 'files' not in request.files:
            return render_template('index.html', error='No files were selected.')

        files = request.files.getlist('files')

        # Check if any file was uploaded
        if len(files) == 0:
            return render_template('index.html', error='No files were selected.')

        # Create temporary folder if it doesn't exist
        if not os.path.exists(app.config['TEMP_FOLDER']):
            os.makedirs(app.config['TEMP_FOLDER'])

        # Save uploaded files to temporary folder
        filenames = []
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['TEMP_FOLDER'], filename)
                file.save(file_path)
                filenames.append(filename)

        # Create output folder if it doesn't exist
        if not os.path.exists(app.config['OUTPUT_FOLDER']):
            os.makedirs(app.config['OUTPUT_FOLDER'])

        # Convert each uploaded file to H.264 and VP8 formats
        converted_files = []
        for filename in filenames:
            file_path = os.path.join(app.config['TEMP_FOLDER'], filename)
            tablet_height = 800  # Adjust the height for tablets
            ipad_height = 1536  # Adjust the height for iPads
            tablet_resolution = get_scaled_resolution(file_path, tablet_height)
            ipad_resolution = get_scaled_resolution(file_path, ipad_height)
            if tablet_resolution:
                converted_file = convert_video_to_vp8(file_path, app.config['OUTPUT_FOLDER'], tablet_resolution)  # Convert to webm for tablets
                converted_files.append(converted_file)
            if ipad_resolution:
                converted_file = convert_video_to_h264(file_path, app.config['OUTPUT_FOLDER'], ipad_resolution)  # Convert to mp4 for iPad
                converted_files.append(converted_file)
        # Create a zip file containing the converted files
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_string = generate_random_string(6)
        zip_filename = f'converted_files_{timestamp}_{random_string}.zip'
        zip_filepath = os.path.join(app.config['OUTPUT_FOLDER'], zip_filename)
        # Schedule the file deletion job if it's not already scheduled
        with zipfile.ZipFile(zip_filepath, 'w') as zip_file:
            for converted_file in converted_files:
                zip_file.write(converted_file, os.path.basename(converted_file))
        # Send the zip file as a download
        if not scheduler.get_jobs():
            scheduler.add_job(delete_files, 'date', run_date=datetime.now() + timedelta(minutes=1), args=[zip_filepath])
            scheduler.start()
        return send_file(zip_filepath, as_attachment=True)

    return render_template('index.html')



# ...

if __name__ == '__main__':
    app.run(debug=True)