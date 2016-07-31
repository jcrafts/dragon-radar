import os
import shutil
import logging
import tempfile
import atexit
import subprocess
from constants import Constants
from utils import delete_temp, create_dir, move_file

APP_NAME = Constants.APP_NAME
FRAME_RATE = Constants.FRAME_RATE
DELAYCUT_CMD = '{delaycut} -i {i} -endcut {end} -startcut {begin} -o {o}'
AC3_DIR = Constants.AC3_DIR

logger = logging.getLogger(APP_NAME)


def frame_to_ms(frame, offset):
    if frame == 0:
        prev_chapter_end = 0
    else:
        prev_chapter_end = int(
            round(1000 * float(frame - 1) / FRAME_RATE, 0))
    if int(offset) > -1:
        chapter_begin = int(
            round(1000 * float(frame + offset) / FRAME_RATE, 0))
        delay = 0
    else:
        chapter_begin = int(round(1000 * float(frame) / FRAME_RATE, 0))
        delay = int(round(-1000 * float(offset) / FRAME_RATE, 0))
    return prev_chapter_end, chapter_begin, delay


def run_delaycut(delaycut, file_in, prev_ch_end, ch_begin, delay, bitrate):
    file_out_1 = file_in + '.part1'
    file_out_2 = file_in + '.part2'
    file_out_3 = file_in + '.part3'
    print(prev_ch_end, ch_begin, delay)
    if prev_ch_end == 0:
        # initial offset
        logger.debug('Cutting initial part...')
        subprocess.run([delaycut, '-i', file_in, '-endcut', str(prev_ch_end),
                        '-startcut', str(ch_begin), '-o', file_out_1])
        # remove the initial file and begin again
        os.remove(file_in)
        os.rename(file_out_1, file_in)

    else:
        # episode up until chapter point
        logger.debug('Cutting first part...')
        subprocess.run([delaycut, '-i', file_in, '-endcut', str(prev_ch_end),
                        '-startcut', '0', '-o', file_out_1])
        # episode from chapter until end with offset applied
        logger.debug('Cutting second part...')
        subprocess.run([delaycut, '-i', file_in, '-endcut', '0',
                        '-startcut', str(ch_begin), '-o', file_out_3])
        if delay > 0:
            # bitrate = '51_448'
            # need to add blank space between cuts
            logger.debug('Cutting blank delay...')
            logger.debug('Using %s kbps blank ac3.', bitrate)
            blank_file = os.path.join(AC3_DIR, 'blank_' + bitrate + '.ac3')
            subprocess.run([delaycut, '-i', blank_file, '-endcut', str(delay),
                            '-startcut', '0', '-o', file_out_2])
        file_combine = []
        file_combine.append(file_out_1)
        if os.path.isfile(file_out_2):
            file_combine.append(file_out_2)
        file_combine.append(file_out_3)

        logger.debug('Writing combined audio...')

        # delete file before re-creating it
        os.remove(file_in)
        with open(file_in, 'wb') as final_file:
            for fname in file_combine:
                with open(fname, 'rb') as f:
                    shutil.copyfileobj(f, final_file)
        for f in file_combine:
            os.remove(f)


def retime_ac3(episode, src_file, dst_file, bitrate):
    tmp_dir = tempfile.mkdtemp()
    # in the case of unexpected exit, we don't want to
    # keep temp files around
    atexit.register(delete_temp, tmp_dir)
    logging.debug('Audio temp folder: %s', tmp_dir)

    if os.path.isfile(src_file):
        logger.debug('%s found! Proceeding with retiming...', src_file)
    else:
        logger.error('%s not found. Skipping...', src_file)
        return

    try:
        # copy source to tempfile for surgery
        shutil.copy(src_file, tmp_dir)
        working_file = os.path.join(tmp_dir, os.path.basename(src_file))
    except IOError as e:
        logger.error("Unable to copy file. %s", e)
        return

    r2_chaps = episode.r2_chapters
    offsets = episode.offsets

    print(r2_chaps, offsets)

    for key in ['op', 'prologue', 'partB', 'ED', 'NEP']:
        if key in offsets.keys():
            # skip scenes with offset of 0
            if offsets[key]['offset'] == 0:
                continue
            # if key == 'partA':
            #     r2_chaps['partA'] = (offsets['partA']['frame'] -
            #                          (offsets['prologue']['offset'] +
            #                           offsets['op']['offset']))
            chapter = r2_chaps[key]
            offset = offsets[key]['offset']
            prev_chapter_end, chapter_begin, delay = frame_to_ms(chapter,
                                                                 offset)

            run_delaycut(episode.delaycut, working_file, prev_chapter_end,
                         chapter_begin, delay, bitrate)

    move_file(working_file, dst_file)
    delete_temp(tmp_dir)
