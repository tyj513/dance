import os
import subprocess
import cv2
import mediapipe as mp
import numpy as np
import streamlit as st
from statistics import mean
import tempfile
import math
import uuid

# 創建一個臨時目錄
TEMP_DIR = tempfile.mkdtemp()
EXIST_FLAG = "-n"  # ignore existing file, change to -y to always overwrite
SEARCH_INTERVAL = 30  # in secs

# MediaPipe 初始化
mpDraw = mp.solutions.drawing_utils
mpPose = mp.solutions.pose

def safe_filename(filename):
    # 移除非法字符並生成一個唯一的文件名
    return uuid.uuid4().hex + os.path.splitext(filename)[-1]

def get_duration(filename):
    captured_video = cv2.VideoCapture(filename)
    fps = captured_video.get(cv2.CAP_PROP_FPS)
    frame_count = captured_video.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = (frame_count / fps)
    return duration

def get_frame_count(filename):
    captured_video = cv2.VideoCapture(filename)
    frame_count = int(math.floor(captured_video.get(cv2.CAP_PROP_FRAME_COUNT)))
    return captured_video, frame_count

def landmarks(video):
    pose = mpPose.Pose()
    xy_landmark_coords = []
    frames = []
    landmarks = []
    captured_video, frame_count = get_frame_count(video)

    for i in range(frame_count):
        success, image = captured_video.read()
        if not success:
            break
        frames.append(image)
        imgRGB = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        landmarks_in_frame = pose.process(imgRGB)
        landmarks.append(landmarks_in_frame)
        if landmarks_in_frame.pose_landmarks:
            xy_landmark_coords.append([(lm.x, lm.y) for lm in landmarks_in_frame.pose_landmarks.landmark])
        else:
            xy_landmark_coords.append([])

    return xy_landmark_coords, frames, landmarks

def difference(xy1, xy2, frames1, frames2, landmarks1, landmarks2):
    connections = [(16, 14), (14, 12), (12, 11), (11, 13), (13, 15), (12, 24), (11, 23), (24, 23), (24, 26), (23, 25), (26, 28), (25, 27)]
    out_of_sync_frames = 0
    score = 100
    num_of_frames = min(len(xy1), len(xy2))
    
    output_frames = []

    for f in range(num_of_frames):
        percentage_dif_of_frames = []
        p1, p2 = xy1[f], xy2[f]

        if p1 and p2:  # 確保兩個框架都檢測到了姿勢
            for connect in connections:
                j1, j2 = connect
                if j1 < len(p1) and j2 < len(p1) and j1 < len(p2) and j2 < len(p2):
                    try:
                        g1 = (p1[j1][1] - p1[j2][1]) / (p1[j1][0] - p1[j2][0])
                        g2 = (p2[j1][1] - p2[j2][1]) / (p2[j1][0] - p2[j2][0])
                        dif = abs((g1 - g2) / g1) if g1 != 0 else 0
                        percentage_dif_of_frames.append(abs(dif))
                    except ZeroDivisionError:
                        continue

            if percentage_dif_of_frames:
                frame_dif = mean(percentage_dif_of_frames)
            else:
                frame_dif = 0

            frame_height, frame_width, _ = frames1[f].shape
            if landmarks1[f].pose_landmarks:
                mpDraw.draw_landmarks(frames1[f], landmarks1[f].pose_landmarks, mpPose.POSE_CONNECTIONS)
            if landmarks2[f].pose_landmarks:
                mpDraw.draw_landmarks(frames2[f], landmarks2[f].pose_landmarks, mpPose.POSE_CONNECTIONS)
            display = np.concatenate((frames1[f], frames2[f]), axis=1)

            colour = (0, 0, 255) if frame_dif > 10 else (255, 0, 0)

            cv2.putText(display, f"Diff: {frame_dif:.2f}", (40, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, colour, 3)

            if frame_dif > 10:
                out_of_sync_frames += 1

            score = ((f+1 - out_of_sync_frames) / (f+1)) * 100.0
            cv2.putText(display, f"Score: {score:.2f}%", (frame_width +40, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, colour, 3)

            output_frames.append(display)

    # 創建輸出視頻
    output_path = os.path.join(r"C:\Users\ben20415\desktop", "output_comparison.mp4")
    if output_frames:
        out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), 30, (frame_width*2, frame_height))
        for frame in output_frames:
            out.write(frame)
        out.release()

    return score, output_path

def convert_to_same_framerate(clip):
    clip_name = safe_filename(os.path.basename(clip))
    clip_24 = os.path.join(TEMP_DIR, clip_name + '_24.mp4')
    os.system(f'ffmpeg {EXIST_FLAG} -i "{clip}" -filter:v fps=24 "{clip_24}"')
    return clip_24

def validate_reference_clip(ref_clip, comparison_clip):
    _, ref_clip_frame_count = get_frame_count(ref_clip)
    _, comparison_clip_frame_count = get_frame_count(comparison_clip)
    if not (ref_clip_frame_count > comparison_clip_frame_count):
        st.error(f"Reference clip must be longer than comparison clip")
        st.stop()

def convert_to_wav(clip):
    clip_name = safe_filename(os.path.basename(clip))
    clip_wav = os.path.join(TEMP_DIR, clip_name + '.wav')
    command = f'ffmpeg {EXIST_FLAG} -i "{clip}" "{clip_wav}"'
    os.system(command)
    return clip_wav

def find_sound_offset(ref_wav, comparison_wav):
    start_position = 0
    command = f"C:\\Praat.exe --run crosscorrelate.praat {ref_wav} {comparison_wav} {start_position} {SEARCH_INTERVAL}"
    
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        st.error("Error running Praat script")
        st.stop()
    
    offset_str = result.stdout.strip()
    offset_str = ''.join(char for char in offset_str if char.isdigit() or char in '.-')
    
    try:
        return abs(float(offset_str))
    except ValueError as e:
        st.error(f"Error converting offset to float. Cleaned offset: {offset_str}")
        st.stop()

def trim_clips(ref_clip, comparison_clip, offset):
    duration = get_duration(comparison_clip)

    ref_name = safe_filename(os.path.basename(ref_clip))
    comp_name = safe_filename(os.path.basename(comparison_clip))

    ref_cut = os.path.join(TEMP_DIR, ref_name + '_cut.mp4')
    comparison_cut = os.path.join(TEMP_DIR, comp_name + '_cut.mp4')

    command = f'ffmpeg {EXIST_FLAG} -i "{ref_clip}" -ss {offset} -t {duration} "{ref_cut}"'
    os.system(command)
    command = f'ffmpeg {EXIST_FLAG} -i "{comparison_clip}" -ss 0 -t {duration} "{comparison_cut}"'
    os.system(command)

    return ref_cut, comparison_cut

def main():
    st.title("Dance Comparison App")

    # 文件上傳
    ref_clip = st.file_uploader("Upload reference video", type=["mp4", "mov"])
    comparison_clip = st.file_uploader("Upload comparison video", type=["mp4", "mov"])
    
    if ref_clip and comparison_clip:
        # 保存上傳的文件
        ref_path = os.path.join(TEMP_DIR, safe_filename(ref_clip.name))
        comp_path = os.path.join(TEMP_DIR, safe_filename(comparison_clip.name))
        
        with open(ref_path, "wb") as f:
            f.write(ref_clip.getbuffer())
        with open(comp_path, "wb") as f:
            f.write(comparison_clip.getbuffer())

        # 處理視頻
        if st.button("Compare Videos"):
            with st.spinner("Processing videos..."):
                ref_clip_24 = convert_to_same_framerate(ref_path)
                comparison_clip_24 = convert_to_same_framerate(comp_path)

                validate_reference_clip(ref_clip_24, comparison_clip_24)

                ref_clip_wav = convert_to_wav(ref_clip_24)
                comparison_clip_wav = convert_to_wav(comparison_clip_24)

                offset = find_sound_offset(ref_clip_wav, comparison_clip_wav)
                ref_cut, comparison_cut = trim_clips(ref_clip_24, comparison_clip_24, offset)

                xy_dancer1, dancer1_frames, dancer1_landmarks = landmarks(ref_cut)
                xy_dancer2, dancer2_frames, dancer2_landmarks = landmarks(comparison_cut)

                score, output_video = difference(xy_dancer1, xy_dancer2, dancer1_frames, dancer2_frames, dancer1_landmarks, dancer2_landmarks)
            print(output_video)
            st.success(f"Sync Score: {score:.2f}%")
            st.video(output_video)

        # 清理臨時文件
        for file in os.listdir(TEMP_DIR):
            os.unlink(os.path.join(TEMP_DIR, file))
        os.rmdir(TEMP_DIR)

if __name__ == "__main__":
    main()