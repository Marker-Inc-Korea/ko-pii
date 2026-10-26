import spacy
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import SpacyNlpEngine
from presidio_anonymizer import AnonymizerEngine

from ko_pii.integrations.presidio_plugin import KPiiRecognizer


class KoreanRuleEngine(SpacyNlpEngine):
    def load(self):
        # Tokenization only: no model download or statistical NER.
        self.nlp = {"ko": spacy.blank("xx")}


engine = KoreanRuleEngine(models=[{"lang_code": "ko", "model_name": "blank"}])
registry = RecognizerRegistry(supported_languages=["ko"])
registry.add_recognizer(KPiiRecognizer(include=["EMAIL", "PHONE"]))
analyzer = AnalyzerEngine(
    nlp_engine=engine, registry=registry, supported_languages=["ko"],
)
text = "demo@example.com / 010-2345-6789"
results = analyzer.analyze(text=text, language="ko")
print(AnonymizerEngine().anonymize(text=text, analyzer_results=results).text)
