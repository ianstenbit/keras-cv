# Copyright 2022 The KerasCV Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""UNet models for KerasCV.

Reference:
  - [U-Net: Convolutional Networks for Biomedical Image Segmentation](https://arxiv.org/pdf/1505.04597.pdf)
"""

from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras import regularizers
from tensorflow.keras import initializers

def UPillarBlock(filters, downsample):
    def apply(x):
        input_depth = x.shape.as_list()[-1]
        stride = 2 if downsample else 1

        residual = x

        x = layers.Conv2D(filters, 3, stride, padding='same', kernel_initializer=initializers.VarianceScaling(), kernel_regularizer=regularizers.L2(l2=1e-4))(x)
        x = layers.BatchNormalization(synchronized=True, beta_regularizer=regularizers.L2(l2=1e-8), gamma_regularizer=regularizers.L2(l2=1e-8))(x)
        x = layers.ReLU()(x)

        x = layers.Conv2D(filters, 3, 1, padding='same', kernel_initializer=initializers.VarianceScaling(), kernel_regularizer=regularizers.L2(l2=1e-4))(x)
        x = layers.BatchNormalization(synchronized=True, beta_regularizer=regularizers.L2(l2=1e-8), gamma_regularizer=regularizers.L2(l2=1e-8))(x)

        if downsample:
            residual = layers.MaxPool2D(pool_size=2, strides=2, padding='SAME')(residual)

        if input_depth != filters:
            residual = layers.Conv2D(filters, 1, 1, padding='same', kernel_initializer=initializers.VarianceScaling(), kernel_regularizer=regularizers.L2(l2=1e-4))(residual)

        x = x + residual
        x = layers.ReLU()(x)

        return x

    return apply

def SkipBlock(filters):
    def apply(x):
        x = layers.Conv2D(
            filters, 1, 1, kernel_initializer=initializers.VarianceScaling(), kernel_regularizer=regularizers.L2(l2=1e-4)
        )(x)
        x = layers.BatchNormalization(synchronized=True, beta_regularizer=regularizers.L2(l2=1e-8), gamma_regularizer=regularizers.L2(l2=1e-8))(x)
        x = layers.ReLU()(x)

        return x

    return apply

def DownSampleBlock(filters, num_blocks):
    def apply(x):
        x = UPillarBlock(filters, downsample=True)(x)

        for _ in range(num_blocks-1):
            x = UPillarBlock(filters)(x)

        return x

    return apply

def UpSampleBlock(filters):
    def apply(x, lateral_input):
        x = layers.Conv2DTranspose(
          filters, 3, 2, padding='same', kernel_initializer=initializers.VarianceScaling(), kernel_regularizer=regularizers.L2(l2=1e-4)
        )(x)
        x = layers.BatchNormalization(synchronized=True, beta_regularizer=regularizers.L2(l2=1e-8), gamma_regularizer=regularizers.L2(l2=1e-8))(x)
        x = layers.ReLU()(x)

        lateral_input = SkipBlock(filters)(lateral_input)

        x = x + lateral_input
        x = UPillarBlock(filters, downsample=False)

        return x

    return apply

def UNet(down_blocks, up_blocks):
    def apply(x):
        skip_connections = []
        for filters, num_blocks in down_blocks:
            skip_connections.append(x)
            x = DownSampleBlock(filters, num_blocks)(x)

        for filters in up_blocks:
            x = UpSampleBlock(filters)(x, skip_connections.pop())

        return x

    return apply

def ResidualBlock(width):
    def apply(x):
        input_width = x.shape[3]
        if input_width == width:
            residual = x
        else:
            residual = layers.Conv2D(width, kernel_size=1)(x)
        x = layers.BatchNormalization(center=False, scale=False)(x)
        x = layers.Conv2D(
            width, kernel_size=3, padding="same", activation=keras.activations.swish
        )(x)
        x = layers.Conv2D(width, kernel_size=3, padding="same")(x)
        x = layers.Add()([x, residual])
        return x

    return apply

def DownBlock(width, block_depth, block_scale_factor):
    def apply(x):
        x, skips = x
        for index in range(block_depth):
            x = ResidualBlock(width)(x)
        skips.append(x)
        x = layers.AveragePooling2D(pool_size=block_scale_factor)(x)
        return x

    return apply


def UpBlock(width, block_depth, block_scale_factor, include_skip_connections, skip_block):
    def apply(x):
        x, skips = x
        x = layers.UpSampling2D(size=block_scale_factor, interpolation="bilinear")(x)
        if include_skip_connections:
            x = layers.Concatenate()([x, skip_block(width)(skips.pop())])
        for index in range(block_depth):
            x = ResidualBlock(width)(x)
        return x

    return apply


def UNet(
    include_rescaling,
    block_widths=None,
    down_block_widths=None,
    up_block_widths=None,
    block_depth=2,
    bottleneck_width=None,
    bottleneck_depth=None,
    block_scale_factor=2,
    input_shape=(224, 224, 3),
    output_channels=3,
    include_skip_connections=False,
    skip_block=None,
    weights=None,
    name="Unet",
    output_activation=None,
):

    if include_skip_connections and block_widths is None:
        raise ValueError(
            "`include_skip_connections` can only be used with a symmetrical UNet using `block_widths`."
        )

    if block_widths is None and down_block_widths is None and up_block_widths is None:
        raise ValueError(
            "Either `block_widths` or one of `down_block_widths` and `up_block_widths` must be specified."
        )

    if block_widths and (down_block_widths or up_block_widths):
        raise ValueError(
            "When `block_widths` is specified, neither of `down_block_widths` and `up_block_widths` should be specified"
        )

    if not ((block_widths is None) ^ (bottleneck_width is None)):
        raise ValueError(
            "`bottleneck_width` must be specified when using `down_block_widths` and/or `up_block_widths`, but not when using `block_widths`"
        )

    if skip_block and not include_skip_connections:
        raise ValueError(
            "`skip_block` should be defined iff `include_skip_connections=True`"
        )

    if block_widths:
        down_block_widths = block_widths[:-1]
        bottleneck_width = block_widths[-1]
        up_block_widths = reversed(block_widths[:-1])

    if bottleneck_depth is None:
        bottleneck_depth = block_depth

    inputs = layers.Input(input_shape)
    x = inputs

    if include_rescaling:
        x = layers.Rescaling(1 / 255.0)(x)

    skip_connections = []
    if down_block_widths:
        for width in down_block_widths:
            x = DownBlock(width, block_depth, block_scale_factor)([x, skip_connections])

    for _ in range(bottleneck_depth):
        x = ResidualBlock(bottleneck_width)(x)

    if up_block_widths:
        for width in up_block_widths:
            x = UpBlock(
                width, block_depth, block_scale_factor, include_skip_connections
            )([x, skip_connections])

    x = layers.Conv2D(
        output_channels,
        kernel_size=1,
        kernel_initializer="zeros",
        activation=output_activation,
    )(x)

    model = keras.Model(inputs, x, name=name)

    if weights is not None:
        model.load_weights(weights)

    return model
