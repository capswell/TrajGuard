"""Stream an attributed three-camera preview from accepted TrajGuard artifacts."""
import argparse
import io
import json
from pathlib import Path

import h5py
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def decode(row, swap_rb):
    image = Image.open(io.BytesIO(np.asarray(row, dtype=np.uint8).tobytes())).convert('RGB')
    if swap_rb:
        r, g, b = image.split()
        image = Image.merge('RGB', (b, g, r))
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--stride', type=int, default=4)
    parser.add_argument('--fps', type=int, default=25)
    parser.add_argument('--swap-rb', action='store_true', help='Explicit sample-specific JPEG color correction')
    parser.add_argument('--font', default='C:/Windows/Fonts/segoeui.ttf')
    args = parser.parse_args()
    if args.stride < 1 or args.fps < 1:
        parser.error('stride and fps must be positive')
    manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    jobs = [j for j in manifest['jobs'].values() if j['status'] == 'accepted']
    if not jobs:
        raise ValueError('No accepted artifacts')
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fonts = {size: ImageFont.truetype(args.font, size) for size in (16, 20, 25, 38)}
    writer = imageio_ffmpeg.write_frames(str(output), (1280, 800), fps=args.fps,
        codec='libx264', pix_fmt_out='yuv420p', macro_block_size=16,
        output_params=['-crf', '23', '-preset', 'fast', '-movflags', '+faststart'])
    writer.send(None)
    count = 0
    records = []
    try:
        for job in jobs:
            with h5py.File(job['artifact'], 'r') as data:
                length = len(data['state'])
                cameras = ['cam_high', 'cam_left_wrist', 'cam_right_wrist']
                indices = list(range(0, length, args.stride))
                records.append({'source': Path(job['source']).name, 'signature': job['signature'],
                    'source_frames': length, 'preview_frames': len(indices), 'alignment': job['alignment']['mode']})
                for index in indices:
                    canvas = Image.new('RGB', (1280, 800), '#0c1424')
                    draw = ImageDraw.Draw(canvas)
                    draw.text((32, 15), 'TrajGuard', font=fonts[38], fill='#f4f7fc')
                    draw.text((253, 32), 'MULTIMODAL TRAJECTORY PIPELINE', font=fonts[20], fill='#849bb9')
                    draw.rounded_rectangle((1060, 20, 1248, 60), radius=12, fill='#123f36')
                    draw.text((1080, 27), 'QC  /  ACCEPTED', font=fonts[20], fill='#6ee7bd')
                    draw.text((32, 76), f"{Path(job['source']).stem}  /  frame {index:04d} of {length}  /  3 cameras", font=fonts[20], fill='#b7c9df')
                    draw.text((848, 76), f"14D state + action  |  {job['alignment']['mode']}", font=fonts[20], fill='#b7c9df')
                    for camera, box in zip(cameras, [(32, 110, 800, 600), (848, 110, 400, 300), (848, 410, 400, 300)]):
                        x, y, width, height = box
                        frame = decode(data[f'images/{camera}'][index], args.swap_rb)
                        canvas.paste(frame.resize((width, height), Image.Resampling.LANCZOS), (x, y))
                        draw.rectangle((x, y, x+width, y+31), fill='#162238')
                        draw.text((x+12, y+3), camera, font=fonts[20], fill='#e8f0fc')
                    draw.rounded_rectangle((32, 728, 1248, 734), radius=3, fill='#253650')
                    draw.rounded_rectangle((32, 728, 32+int(1216*(index+1)/length), 734), radius=3, fill='#58d7c3')
                    draw.text((32, 746), f'Processed HDF5 preview  |  stride {args.stride}  |  {args.fps} fps playback (not acquisition timing)', font=fonts[16], fill='#a6bad2')
                    draw.text((32, 771), 'Data: public ALOHA demonstrations  /  Processing & visualization: TrajGuard', font=fonts[16], fill='#8197b4')
                    writer.send(np.asarray(canvas).tobytes())
                    if count == 100:
                        canvas.save(output.with_suffix('.jpg'), quality=92)
                    count += 1
                print(f"Rendered {Path(job['source']).name}: {len(indices)} frames", flush=True)
    finally:
        writer.close()
    metadata = {'video': output.name, 'frames': count, 'fps': args.fps,
        'duration_seconds': count/args.fps, 'stride': args.stride, 'swap_rb': args.swap_rb,
        'resolution': [1280, 800], 'episodes': records,
        'note': 'Preview sampled from processed artifacts; playback is not physical timing. No VLM labels.'}
    output.with_suffix('.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
