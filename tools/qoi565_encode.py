#!/usr/bin/env python3

# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (C) 2022 Daniel Thompson

import argparse
from PIL import Image

"""
QOI565 format

This is a modified variant of the "Quite OK Image" (QOI) format by
Dominic Szablewski. It reduces the color range to RGB565.
This modifies RGB chunks to this:

.- QOI_OP_RGB ----------------------------------------------------.
|         Byte[0]         |      Byte[1]      |      Byte[2]      |
|  7  6  5  4  3  2  1  0 | 7 6 5 4 3 | 2 1 0 | 7 6 5 | 4 3 2 1 0 |
|-------------------------+-----------+-------+-------+-----------|
|  1  1  1  1  1  1  1  0 |   red     |    green      |   blue    |
`-----------------------------------------------------------------`

It also defines the `channels` value of 200 for the header to indicate
the QOI565 format. This is not part of the official specification.
Furthermore it doesn't support RGBA and simply discards the alpha values.

Code is based on https://github.com/phoboslab/qoi/blob/master/qoi.h
"""

QOI_OP_INDEX = 0x00  # 00xxxxxx
QOI_OP_DIFF =  0x40  # 01xxxxxx
QOI_OP_LUMA =  0x80  # 10xxxxxx
QOI_OP_RUN =   0xc0  # 11xxxxxx
QOI_OP_RGB =   0xfe  # 11111110
QOI_OP_RGBA =  0xff  # 11111111


def encode(fname):
    im = Image.open(fname)
    width = im.width
    height = im.height
    pixels = im.load()
    prev_value = -1
    prev_rgb565 = (-1, -1, -1)
    run = 0
    index = [0] * 64
    ret = []

    # QOI565 header
    # magic
    ret.append(ord('q'))
    ret.append(ord('o'))
    ret.append(ord('i'))
    ret.append(ord('f'))
    # width (4 bytes, Big Endian)
    ret.append(width >> 24      )
    ret.append(width >> 16 & 255)
    ret.append(width >> 8  & 255)
    ret.append(width       & 255)
    # height (4 bytes, Big Endian)
    ret.append(height >> 24      )
    ret.append(height >> 16 & 255)
    ret.append(height >> 8  & 255)
    ret.append(height       & 255)
    # channels
    ret.append(200)  # 3 = RGB, 4 = RGBA, 200 = RGB565 (custom)
    # colorspace
    ret.append(0)  # 0 = sRGB, 1 = all linear

    for y in range(height):
        for x in range(width):
            try:
                # try RGBA
                r, g, b, _ = pixels[x, y]
            except ValueError:
                # try RGB
                r, g, b = pixels[x, y]

            # convert to RGB565
            r5 = r >> 3
            g6 = g >> 2
            b5 = b >> 3
            value = (r5 << 11) | (g6 << 5) | b5

            if prev_value == value:
                # when the previous pixel matches the current, start counting
                # repeated occurences for the RUN operator
                run += 1
                # limit of RUN is 62 repetitions or end of image
                if run == 62 or (x == width-1 and y == height-1):
                    ret.append(QOI_OP_RUN | (run - 1))
                    run = 0
            else:
                if run > 0:
                    # if a RUN counter is active but this pixel is different,
                    # conclude the RUN operator and then proceed with the
                    # current pixel normally
                    ret.append(QOI_OP_RUN | (run - 1))
                    run = 0

                # hash function for the runtime index array
                index_pos = (r5 * 3 + g6 * 5 + b5 * 7) % 64

                # check if pixel matches previously seen one with same hash
                if index[index_pos] == value:
                    # if entry matches, encode this with the INDEX operator
                    # using 1 byte
                    ret.append(QOI_OP_INDEX | index_pos)
                else:
                    # write this seen pixel to the index
                    index[index_pos] = value

                    pr, pg, pb = prev_rgb565
                    vr = r5 - pr
                    vg = g6 - pg
                    vb = b5 - pb

                    vg_r = vr - vg
                    vg_b = vb - vg

                    # if the diff to the previous pixel is quite small, the
                    # DIFF operator will be sufficient, encoded into 1 byte
                    if (
                        vr > -3 and vr < 2 and
                        vg > -3 and vg < 2 and
                        vb > -3 and vb < 2
                    ):
                        ret.append(
                            QOI_OP_DIFF
                            | (vr + 2) << 4 | (vg + 2) << 2 | (vb + 2)
                        )
                    # if the diff to the previous pixel is larger but still
                    # within a certain range, the LUMA operator can encode
                    # it into 2 bytes
                    elif (
                        vg_r >  -9 and vg_r <  8 and
                        vg   > -33 and vg   < 32 and
                        vg_b >  -9 and vg_b <  8
                    ):
                        ret.append(QOI_OP_LUMA | (vg   + 32))
                        ret.append((vg_r + 8) << 4 | (vg_b + 8))
                    # if none of the diff operators can encode the change
                    # relative to the previous pixel, encode it with the
                    # RGB565 operator, using 3 bytes
                    else:
                        ret.append(QOI_OP_RGB)
                        # 1st byte = all 5 bits of r5 + first 3 bits of g6
                        ret.append(r5 << 3 | g6 >> 3)
                        # 2nd byte = last 3 bit of g6 + all 5 bits of b5
                        # (the bitwise AND with 255 cuts down to 8 bits)
                        ret.append((g6 << 5 | b5) & 255)

            prev_value = value
            prev_rgb565 = (r5, g6, b5)

        # TODO: implement 8-byte end marker

    with open(fname + '.qoi', 'wb') as outfile:
        outfile.write(bytes(ret))


parser = argparse.ArgumentParser(description='QOI565 encoder tool.')
parser.add_argument('files', nargs='*',
                    help='files to be encoded')

args = parser.parse_args()

for fname in args.files:
    encode(fname)
