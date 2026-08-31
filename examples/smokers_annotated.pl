ce_mark("D"). person(alice). 
ce_mark("D"). person(bob). 
ce_mark("D"). person(charlie).
ce_mark("A"). person(debbie).
0.5::stress(X) :- person(X).
ce_mark("S"). 0.4::influences(X,Y) :- person(X), person(Y).
friend(bob, alice).
smokes(alice).
smokes(X) :- stress(X).
smokes(X) :- friend(X,Y), influences(Y,X), smokes(Y).

foil(smokes(bob), 0.5,0.5).
foil(smokes(charlie),0.5, 0.5).
