# Making STM more approachable

This repository is an attempt attempt at creating a Python based interface
for pre-processing a corpus and managing how it is processed in the R-based
Structural Topic Model library [_stm_](https://cran.r-project.org/web/packages/stm/index.html). The interface from Python to R has been managed through the [_rpy2_](https://pypi.org/project/rpy2/)

It has been constructed with a very corpus in mind, an excerpt from the
[_Monastica_](https://monastca.ht.lu.se) database.
However, the interface could be readapted for other copora with little effort.

This repository was written with the intention of making Structural Topic
Modelling more accessible to the researchers of the
__Authoroty, community, and individual freedom - Latin monastic culture and
the roots of European educational ideals
([__ELAM__](https://projekt.ht.lu.se/monasticism)
project located at [Lund University](https://portal.research.lu.se/sv/projects/authority-community-and-individual-freedom-latin-monastic-culture)).
The project is financed [Riksbankens Jubileumsfond](https://www.rj.se/anslag/2021/auktoritet-samhalle-och-individuell-frihet--det-latinska-klostervasendet-och-rotterna-till-europas-utbildningsideal/).


## Corpus compilation

The raw excerpt from the [_Monastica_](https://monastca.ht.lu.se) contains
details on the paragraph level of the various texts, all of which has been
preserved as they were entered into a single-table
[SQLite3](https://www.sqlite.org) database from which the texts can easily be
aggregated into their full forms. In addition to keeping each paragraph in its
raw format a lemmatized
(processed with [lamonpy](https://pypi.org/project/lamonpy)) copy is stored in
parallel -- this enables the user to use either the raw or the lemmatized
version without having to wait for the lemmatizer.

## The interface

The interface is divided into three main parts:
1. Pre-processing the corpus
2. Configuring a STM-model
3. Exploring the fitted model through graphs

Each of these three parts has a small number of settings and a button that
executes that part's function with the settings. All results, or close
thereto, are stored on disk and reloaded when the same settings are used again.
The idea behind this is to allow for simple exploration of the data, try
different approaches and switch between them without having to wait for it to
recaltulate.

### Pre-processing

a. Select whether to aggregate the texts on:
    - Paragraph
    - Title
    - Author
b. Select wether to use the raw paragraphs or the lemmatized paragraphs
c. Select a minimum token length (default 1), discard everything shorter
b. Update the stopwords list.
    - The default stopwords list has been retreived from [aurelberra/stopwords](https://github.com/aurelberra/stopwords/blob/master/stopwords_latin.txt)
    - The stopwords can be updated and changed, duplicates are automatically removed.

Pressing the "save setting" button will load a corpus fitting the selected
settings into memory -- either by loading it from disk or creating it. All
created corpora versions are saved to disk for later loading.

### Model fitting

Four parameters are available for adjustment:
a. Select the number of topics
b. The maximum number of iterations to consider
c. Whether to introduce the author as a parameter
d. Whether to introduce the work(by title) as a parameter

Pressing the "Fit stm" button will initialize the calculation, which can take
several minutes to complete.

### Plotting

In this final portion of the interface the fitted model and corpus can be
explored through a small set of simple plots. First, select which topics you want to visualize through the checkboxes on the right -- they are all turned off by default.


There is currently support five types of graphs:
a. "default"
    This plot show each topic's nr, top 3 associated words and show their
    expected proportion in the corpus.

b. "hist"
    Shows a histogram of the MAP estimates of the document-topic, where the
    dashed red line denotes the median.

c. "perspectives"
    A comparison of two topics (the lowest two if more than two are selected)
    , where words associated with either topics are positioned across the
    x-axis accordng to which topic they have the strongest association.
    The size of the word is an indication of its frequency.

d. "labels"
    Shows the selected topics and their top associated words.

d. "topicCorr"
    Shows a graph of the correlation between topics.
