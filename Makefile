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

# an archive of source code.
ar.txz: $(TEXSRC) main.bib
	tar cJvf ar.txz main.tex ./src main.bib neurips_2025.sty

.PHONY: clean
clean:
	- rm -f *.aux *.bbl *.blg *.log *.out

