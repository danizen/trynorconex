#!/usr/bin/env python

from __future__ import print_function, division
from __future__ import absolute_import, unicode_literals

from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.stemmers import Stemmer
from sumy.nlp.tokenizers import Tokenizer
from sumy.utils import get_stop_words
from sumy.summarizers.lex_rank import LexRankSummarizer
from elasticsearch import Elasticsearch
import argparse
from os.path import basename
import sys
import json


LANGUAGE_MAP = {
    'en': 'english',
    'es': 'spanish'
}


class Enricher(object):
    """
    Knows how to enrich a set of fields with a summary and maybe other stuff
    """

    def __init__(self, content_field='content', lang_field='language', count=10):
        self.lang_field = lang_field
        self.content_field = content_field
        self.count = count

    def summarize(self, fields):
        """
        yields the summary on a hit to facilitate building bulk update
        """
        assert self.content_field in fields
        content = fields[self.content_field][0]
        language = fields[self.lang_field][0] if self.lang_field in fields else 'en'
        language = LANGUAGE_MAP[language]
        parser = PlaintextParser.from_string(content, Tokenizer(language))
        stemmer = Stemmer(language)
        summarizer = LexRankSummarizer(stemmer)
        summarizer.stop_words = get_stop_words(language)

        sentences = [str(s) for s in summarizer(parser.document, self.count)]
        summary = ' '.join(sentences)
        return summary


def parse_arguments(args):
    prog_name = basename(__file__)
    parser = argparse.ArgumentParser(
        prog=prog_name,
        description="Enhance elastic search index with summaries",
    )
    parser.add_argument(
        '--index', '-i', metavar='NAME', required=True,
        help="The elastic search index to use",
    )
    parser.add_argument(
        '--type', '-t', metavar='TYPE', required=True,
        help="The type to enhance",
    )
    parser.add_argument(
        '--textfld', metavar="FIELDNAME", default="content",
        help="The name of the content field",
    )
    parser.add_argument(
        '--langfld', metavar="FIELDNAME", default='language',
        help="The name of the language field",
    )
    parser.add_argument(
        '--count', '-c', metavar="COUNT", default=10, type=int,
        help="How many sentences to use for the summary",
    )
    parser.add_argument(
        '--summary', '-s', metavar="FIELDNAME", default="basicsum",
        help="The name of the summary field",
    )
    return parser.parse_args()


def search(es, indexname, typename, count=10):
    # NOTE: multi_match queries default to dis_max,
    #       and that is where the boosts are put, in the fields
    #       parameter.

    # TODO: Use from and size to paginate
    #       Use scroll (see Search API) to paginate all "new" results

    # TODO: Specify the "fields" that we want to get back to avoid
    #       the cost of fetching the "_source".

    # TODO: Use a fitered query to generate results faster, since
    #       we will skip scoring

    # TODO: aggregations are facets.
    body = {
        'query': {
            'filtered': {
                'filter': {
                    'term': {
                        'status': 'new'
                    }
                }
            }
        }
    }
    res = es.search(index=indexname, doc_type=typename, body=body)
    return res


def summarize(hit, enricher):
    assert '_source' in hit
    fields = hit['_source']
    return enricher.summarize(fields)


def main(args):
    opts = parse_arguments(args)
    es = Elasticsearch(hosts=['localhost'])
    res = search(es, opts.index, opts.type, opts.count)
    assert 'hits' in res
    hits = res['hits']
    assert 'total' in hits
    assert 'hits' in hits

    enricher = Enricher(
        content_field=opts.textfld,
        lang_field=opts.langfld,
        count=opts.count,
    )

    for hit in hits['hits']:
        summary = summarize(hit, enricher)
        print('Summary for %s' % hit['_id'])
        print(summary)


if __name__ == '__main__':
    main(sys.argv[1:])
