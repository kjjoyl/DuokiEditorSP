import os
import subprocess

def convert_mp3(input_file, output_file):
    base_duoki_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ffmpeg_path = os.path.join(base_duoki_dir, "resources", "tools", "ffmpeg.exe")
    #print(f"调用ffmpeg: {ffmpeg_path}")
    command = [
        ffmpeg_path, "-i", input_file,
        "-ar", "16000",
        "-ac", "1",
        "-sample_fmt", "s16",
        output_file
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        err = (result.stderr or b"").decode(errors="ignore").strip()
        print(f"转码失败: {input_file}\n错误信息: {err[:512]}")
        return False
    return True

def convert_mp3_to_wav(input_file, output_file):
    base_duoki_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ffmpeg_path = os.path.join(base_duoki_dir, "resources", "tools", "ffmpeg.exe")
    command = [
        ffmpeg_path, "-i", input_file,
        "-ar", "16000",
        "-ac", "1",
        "-sample_fmt", "s16",
        output_file
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        err = (result.stderr or b"").decode(errors="ignore").strip()
        print(f"转为wav失败: {input_file}\n错误信息: {err[:512]}")
        return False
    return True

def convert_all_mp3_in_directory(input_dir, output_dir, recursive, progress_callback=None, output_format="mp3"):
    if not input_dir or not output_dir:
        raise ValueError("input_dir and output_dir are required")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    if not os.path.exists(input_dir):
        print(f"输入目录不存在: {input_dir}")
        return (0, 0)
    files_to_convert = []
    if recursive:
        for root, _, files in os.walk(input_dir):
            for filename in files:
                if filename.lower().endswith(".mp3"):
                    input_file = os.path.join(root, filename)
                    relative_path = os.path.relpath(root, input_dir)
                    output_file_dir = os.path.join(output_dir, relative_path)
                    output_file = os.path.join(output_file_dir, filename)
                    files_to_convert.append((input_file, output_file_dir, output_file))
    else:
        for filename in os.listdir(input_dir):
            p = os.path.join(input_dir, filename)
            if os.path.isfile(p) and filename.lower().endswith('.mp3'):
                output_file_dir = output_dir
                output_file = os.path.join(output_file_dir, filename)
                files_to_convert.append((p, output_file_dir, output_file))
    total = len(files_to_convert)
    converted = 0
    for input_file, output_file_dir, output_file in files_to_convert:
        if not os.path.exists(output_file_dir):
            os.makedirs(output_file_dir)
        if output_format == "mp3":
            ok = convert_mp3(input_file, output_file)
            if ok:
                converted += 1
        else:
            base, _ = os.path.splitext(os.path.basename(output_file))
            wav_path = os.path.join(output_file_dir, base + ".wav")
            ok2 = convert_mp3_to_wav(input_file, wav_path)
            if ok2:
                print(f"生成wav: {wav_path}")
                converted += 1
                if os.path.exists(output_file):
                    try:
                        os.remove(output_file)
                        print(f"已清理中间文件: {output_file}")
                    except Exception as e:
                        print(f"清理中间文件失败: {output_file}, 错误: {str(e)}")
        if callable(progress_callback):
            try:
                progress_callback(converted, total)
            except Exception:
                pass
    #print(f"转码汇总: 已转换 {converted} / 总数 {total}")
    return (converted, total)
