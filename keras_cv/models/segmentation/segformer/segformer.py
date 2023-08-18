import copy

from keras_cv.backend import keras
from keras_cv.models.segmentation.segformer.segformer_presets import (  # noqa: E501
    presets,
)
from keras_cv.models.segmentation.segformer.segformer_presets import (  # noqa: E501
    presets_with_weights,
)
from keras_cv.models.task import Task
from keras_cv.utils.python_utils import classproperty
from keras_cv.utils.train import get_feature_extractor


@keras_cv_export("keras_cv.layers.SegFormer")
class SegFormer(Task):
    """A Keras model implementing the SegFormer architecture for semantic
    segmentation.

    References:
        - [SegFormer: Simple and Efficient Design for Semantic Segmentation with Transformers](https://arxiv.org/abs/2105.15203)
        - [Based on the TensorFlow implementation from DeepVision](https://github.com/DavidLandup0/deepvision/tree/main/deepvision/models/segmentation/segformer)

    Args:
        backbone: `keras.Model`. The backbone network for the model that is
            used as a feature extractor for the SegFormer encoder. It is *intended*
            to be used only with the MiT backbone model which was created specifically
            for SegFormers. It should either be a `keras_cv.models.backbones.backbone.Backbone` or a
            `tf.keras.Model` that implements the `pyramid_level_inputs`
            property with keys "P2", "P3", "P4", and "P5" and layer names as
            values.
        num_classes: int, the number of classes for the detection model. Note
            that the `num_classes` doesn't contain the background class, and the
            classes from the data should be represented by integers with range
            [0, `num_classes`).
        projection_filters: int, default 256, number of filters in the convolution layer
            projecting the concatenated features into a segmentation map.

    Examples:

    Using the class with a `backbone`:

    ```python
    import tensorflow as tf
    import keras_cv

    images = np.ones(shape=(1, 96, 96, 3))
    labels = np.zeros(shape=(1, 96, 96, 1))
    backbone = keras_cv.models.MiTBackbone.from_preset("mit_b0_imagenet")
    model = keras_cv.models.segmentation.SegFormer(
        num_classes=1, backbone=backbone,
    )

    # Evaluate model
    model(images)

    # Train model
    model.compile(
        optimizer="adam",
        loss=keras.losses.BinaryCrossentropy(from_logits=False),
        metrics=["accuracy"],
    )
    model.fit(images, labels, epochs=3)
    ```
    """

    def __init__(
        self,
        backbone,
        num_classes,
        projection_filters=256,
        **kwargs,
    ):
        if not isinstance(backbone, keras.layers.Layer) or not isinstance(
            backbone, keras.Model
        ):
            raise ValueError(
                "Argument `backbone` must be a `keras.layers.Layer` instance "
                f" or `keras.Model`. Received instead "
                f"backbone={backbone} (of type {type(backbone)})."
            )

        inputs = backbone.input

        feature_extractor = get_feature_extractor(
            backbone, list(backbone.pyramid_level_inputs.values())
        )
        # Multi-level dictionary
        features = list(feature_extractor(inputs).values())

        # Get H and W of level one output
        _, H, W, _ = features[0].shape
        # Project all multi-level outputs onto the same dimensionality
        # and feature map shape
        multi_layer_outs = []
        for feature_dim, feature in zip(backbone.embedding_dims, features):
            out = keras.layers.Dense(
                projection_filters, name=f"linear_{feature_dim}"
            )(feature)
            out = keras.layers.Resizing(H, W, interpolation="bilinear")(out)
            multi_layer_outs.append(out)

        # Concat now-equal feature maps
        concatenated_outs = keras.layers.Concatenate(axis=3)(
            multi_layer_outs[::-1]
        )

        # Fuse concatenated features into a segmentation map
        seg = keras.Sequential(
            [
                keras.layers.Conv2D(
                    filters=projection_filters, kernel_size=1, use_bias=False
                ),
                keras.layers.BatchNormalization(),
                keras.layers.Activation("relu"),
            ]
        )(concatenated_outs)

        seg = keras.layers.Dropout(0.1)(seg)
        seg = keras.layers.Conv2D(
            filters=num_classes, kernel_size=1, activation="softmax"
        )(seg)

        output = keras.layers.Resizing(
            height=inputs.shape[1],
            width=inputs.shape[2],
            interpolation="bilinear",
        )(seg)

        super().__init__(
            inputs=inputs,
            outputs=output,
            **kwargs,
        )

        self.num_classes = num_classes
        self.projection_filters = projection_filters

    def get_config(self):
        config = super().get_config()
        config.update(
            {
                "num_classes": self.num_classes,
                "backbone": self.backbone,
                "projection_filters": self.projection_filters,
                "backbone": keras.saving.serialize_keras_object(self.backbone),
            }
        )

    @classproperty
    def presets(cls):
        """Dictionary of preset names and configurations."""
        return copy.deepcopy(presets)

    @classproperty
    def presets_with_weights(cls):
        """Dictionary of preset names and configurations that include
        weights."""
        return copy.deepcopy(presets_with_weights)