# Copyright 2023 The KerasCV Authors
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
"""Image classifier model using pooling and dense layers."""

import copy

from keras import layers
from tensorflow import keras

from keras_cv.models.backbones.backbone_presets import backbone_presets
from keras_cv.models.backbones.backbone_presets import (
    backbone_presets_with_weights,
)
from keras_cv.models.classification.image_classifier_presets import (
    classifier_presets,
)
from keras_cv.models.task import Task
from keras_cv.utils.python_utils import classproperty


@keras.utils.register_keras_serializable(package="keras_cv.models")
class PooledDenseHead(layers.Layer):
    """General purpose head for image classification.

    Applies GlobalAveragePooling followed by a Dense layer mapping to the
    number of classes to the Backbone output.

    Args:
        num_classes: int, number of classes to predict.
        activation: A `str` or callable. The activation function to
            use on the Dense layer. Set `classifier_activation=None` to return
            the logits of the "top" layer.
    """

    def __init__(
        self,
        num_classes=2,
        activation=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.pooling = layers.GlobalAveragePooling2D(name="avg_pool")
        self.dense = layers.Dense(
            num_classes,
            activation=activation,
            name="predictions",
        )
        self.num_classes = num_classes
        self.activation = activation

    def call(self, inputs):
        x = self.pooling(inputs)
        return self.dense(x)

    def get_config(self):
        config = super().get_config()
        config.update(
            {
                "num_classes": self.num_classes,
                "activation": self.activation,
            }
        )
        return config


@keras.utils.register_keras_serializable(package="keras_cv.models")
class ImageClassifier(Task):
    """Image classifier with configurable prediction head.

    Args:
        backbone: `keras_cv.models.Backbone`, the backbone architecture of the
            classifier called on the inputs.
        num_classes: int, number of classes to predict.
        activation: A `str` or callable. The activation function to
            use on the Dense layer. Set `classifier_activation=None` to return
            the logits of the "top" layer.
        head: str or keras.layers.Layer. Prediction head for classifier. If
            string, must be "pooled_dense". If a keras.layers.Layer, must take
            arguments "num_classes" and "activation" and have no other
            positional arguments.

    Example:
    ```python
    input_data = tf.ones(shape=(8, 224, 224, 3))

    # Pretrained backbone
    model = keras_cv.models.ImageClassifier.from_preset(
        "resnet50_v2_imagenet",
        num_classes=4,
    )
    output = model(input_data)

    # Randomly initialized backbone with a custom config
    model = keras_cv.models.ImageClassifier(
        backbone=keras_cv.models.ResNet50V2Backbone(),
        num_classes=4,
    )
    output = model(input_data)
    ```
    """

    def __init__(
        self,
        backbone,
        num_classes=2,
        activation="softmax",
        head="pooled_dense",
        **kwargs,
    ):
        if isinstance(head, str):
            if head == "pooled_dense":
                head = PooledDenseHead
            else:
                ValueError(
                    '`head` must be "pooled_dense" or a keras.layers.Layer. '
                    f"Got: {head}"
                )
        head_fn = head(num_classes, activation)

        inputs = backbone.input
        x = backbone(inputs)
        outputs = head_fn(x)

        # Instantiate using Functional API Model constructor
        super().__init__(
            inputs=inputs,
            outputs=outputs,
            **kwargs,
        )
        # All references to `self` below this line
        self.backbone = backbone
        self.num_classes = num_classes
        self.head_fn = head_fn
        self.activation = activation

        # Default compilation
        self.compile(
            loss="categorical_crossentropy",
            optimizer="adam",
            metrics=["accuracy"],
        )

    def get_config(self):
        config = super().get_config()
        config.update(
            {
                "num_classes": self.num_classes,
                "head_fn": layers.serialize(self.head_fn),
                "activation": self.activation,
            }
        )
        return config
    
    @classmethod
    def from_config(cls, config):
        if "head_fn" in config:
            head_fn = config.pop("head_fn")
            config["head"] = layers.deserialize(head_fn)
        return cls(**config)

    @classproperty
    def presets(cls):
        """Dictionary of preset names and configurations."""
        return copy.deepcopy({**backbone_presets, **classifier_presets})

    @classproperty
    def presets_with_weights(cls):
        """Dictionary of preset names and configurations that include weights."""
        return copy.deepcopy(
            {**backbone_presets_with_weights, **classifier_presets}
        )

    @classproperty
    def backbone_presets(cls):
        """Dictionary of preset names and configurations of compatible backbones."""
        return copy.deepcopy(backbone_presets)
