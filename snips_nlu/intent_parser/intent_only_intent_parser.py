# coding=utf-8
from __future__ import unicode_literals

import json
import logging

from pathlib import Path

from snips_nlu.constants import INTENTS
from snips_nlu.dataset import validate_and_format_dataset
from snips_nlu.intent_parser.intent_parser import IntentParser
from snips_nlu.pipeline.configs.intent_parser import \
    IntentOnlyIntentParserConfig
from snips_nlu.pipeline.processing_unit import (
    build_processing_unit, load_processing_unit)
from snips_nlu.result import empty_result, parsing_result
from snips_nlu.utils import (
    check_persisted_path, fitted_required, json_string, log_elapsed_time,
    log_result)

logger = logging.getLogger(__name__)


class IntentOnlyIntentParser(IntentParser):
    """Intent parser which consists in two steps: intent classification then
    slot filling"""

    unit_name = "intent_only_intent_parser"
    config_type = IntentOnlyIntentParserConfig

    # pylint:disable=line-too-long
    def __init__(self, config=None, **shared):
        """The probabilistic intent parser can be configured by passing a
        :class:`.ProbabilisticIntentParserConfig`"""
        if config is None:
            config = self.config_type()
        super(IntentOnlyIntentParser, self).__init__(config, **shared)
        self.intent_classifier = None

    # pylint:enable=line-too-long

    @property
    def fitted(self):
        """Whether or not the intent parser has already been fitted"""
        return self.intent_classifier is not None \
               and self.intent_classifier.fitted

    @log_elapsed_time(logger, logging.INFO,
                      "Fitted probabilistic intent parser in {elapsed_time}")
    # pylint:disable=arguments-differ
    def fit(self, dataset, force_retrain=True):
        """Fit the slot filler

        Args:
            dataset (dict): A valid Snips dataset
            force_retrain (bool, optional): If *False*, will not retrain intent
                classifier and slot fillers when they are already fitted.
                Default to *True*.

        Returns:
            :class:`ProbabilisticIntentParser`: The same instance, trained
        """
        logger.info("Fitting probabilistic intent parser...")
        dataset = validate_and_format_dataset(dataset)
        self.fit_builtin_entity_parser_if_needed(dataset)
        self.fit_custom_entity_parser_if_needed(dataset)
        intents = list(dataset[INTENTS])
        if self.intent_classifier is None:
            self.intent_classifier = build_processing_unit(
                self.config.intent_classifier_config)
        self.intent_classifier.builtin_entity_parser = \
            self.builtin_entity_parser
        self.intent_classifier.custom_entity_parser = \
            self.custom_entity_parser
        if force_retrain or not self.intent_classifier.fitted:
            self.intent_classifier.fit(dataset)
        return self

    # pylint:enable=arguments-differ

    @log_result(logger, logging.DEBUG,
                "ProbabilisticIntentParser result -> {result}")
    @log_elapsed_time(logger, logging.DEBUG,
                      "ProbabilisticIntentParser parsed in {elapsed_time}")
    @fitted_required
    def parse(self, text, intents=None):
        """Performs intent parsing on the provided *text* by first classifying
        the intent and then using the correspond slot filler to extract slots

        Args:
            text (str): Input
            intents (str or list of str): If provided, reduces the scope of
                intent parsing to the provided list of intents

        Returns:
            dict: The most likely intent along with the extracted slots. See
            :func:`.parsing_result` for the output format.

        Raises:
            NotTrained: When the intent parser is not fitted
        """
        logger.debug("Probabilistic intent parser parsing '%s'...", text)

        if isinstance(intents, str):
            intents = [intents]

        intent_result = self.intent_classifier.get_intent(text, intents)
        if intent_result is None:
            return empty_result(text)
        return parsing_result(text, intent_result, [])

    @check_persisted_path
    def persist(self, path):
        """Persist the object at the given path"""
        path = Path(path)
        path.mkdir()

        if self.intent_classifier is not None:
            self.intent_classifier.persist(path / "intent_classifier")

        model = {
            "config": self.config.to_dict(),
        }
        model_json = json_string(model)
        model_path = path / "intent_parser.json"
        with model_path.open(mode="w") as f:
            f.write(model_json)
        self.persist_metadata(path)

    @classmethod
    def from_path(cls, path, **shared):
        """Load a :class:`ProbabilisticIntentParser` instance from a path

        The data at the given path must have been generated using
        :func:`~ProbabilisticIntentParser.persist`
        """
        path = Path(path)
        model_path = path / "intent_parser.json"
        if not model_path.exists():
            raise OSError("Missing probabilistic intent parser model file: "
                          "%s" % model_path.name)

        with model_path.open(encoding="utf8") as f:
            model = json.load(f)

        parser = cls(config=cls.config_type.from_dict(model["config"]),
                     **shared)
        classifier = None
        intent_classifier_path = path / "intent_classifier"
        if intent_classifier_path.exists():
            classifier = load_processing_unit(intent_classifier_path, **shared)

        parser.intent_classifier = classifier
        return parser
