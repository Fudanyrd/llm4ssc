TEXFLAGS = --halt-on-error
BIBSRC = dataset/*.bib
TEXSRC = main.tex src/*.tex

main.bib: $(BIBSRC)
	cat $^ > $@

main.pdf: $(TEXSRC) main.bib
	pdflatex $(TEXFLAGS) main.tex
	bibtex main.aux
	pdflatex $(TEXFLAGS) main.tex
	pdflatex $(TEXFLAGS) main.tex
