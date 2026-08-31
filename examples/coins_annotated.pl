0.5 :: heads(X) :- coin(X).
tails(X) :- coin(X), not heads(X).

ce_mark("S"). coin(1).
ce_mark("S"). coin(2).
ce_mark("S"). coin(3).

win :- heads(1), heads(2), heads(3).

foil(win, 0.25, 0.25).
