"""
SYNOPSIS
    dedup.py [bibtex file] [increments]
"""

import sys
import os
import bibtexparser
from bibtexparser.bibdatabase import BibDatabase

def _dbg(*args, **kwargs):
    kwargs['file'] = sys.stderr
    print(*args, **kwargs)


class EditDistanceSolver:
    @staticmethod
    def minDistance(word1: str, word2: str) -> int:
        """
        [Credit](https://leetcode.com/problems/edit-distance/solutions/3230662/clean-codes-full-explanation-dynamic-pro-ytsr)
        """
        prev = list(range(len(word2)+1))
        cur = [0] * (len(word2) + 1)

        for i in range(1, len(word1)+1):
            cur[0] = i
            for j in range(1, len(word2)+1):
                if word1[i-1] == word2[j-1]:
                    cur[j] = prev[j-1]
                else:
                    cur[j] = min(prev[j-1] + 1, prev[j] + 1, cur[j-1] + 1)
                
            prev = cur
            cur = [0] * (len(word2) + 1)
        
        return prev[-1]

    @staticmethod
    def test():
        # From leetcode
        assert EditDistanceSolver.minDistance('horse', 'ros') == 3
        assert EditDistanceSolver.minDistance('horse', 'horse') == 0
        assert EditDistanceSolver.minDistance('intention', 'execution') == 5

if __name__ == '__main__':
    # EditDistanceSolver.test()
    ifile = sys.argv[1]
    inc_file = sys.argv[2]

    import os, shutil
    # make a backup of inc_file.
    if os.path.exists(inc_file):
        shutil.copy(inc_file, inc_file + '.bak')

    idb = bibtexparser.load(open(ifile, encoding = 'utf-8'))
    incdb  = bibtexparser.load(open(inc_file, encoding = 'utf-8'))

    notdup = [] 
    for e in incdb.entries:
        isnew = True
        if e['ENTRYTYPE'] == 'proceedings':
            continue
        for exist in idb.entries:
            if 'doi' in e and e['doi'] == exist.get('doi'):
                isnew = False; break
        if isnew:
            notdup.append(e)

    incdb.entries = notdup
    with open(inc_file, 'w',encoding='utf-8')as fobj:
        s = bibtexparser.dump(incdb, fobj)

