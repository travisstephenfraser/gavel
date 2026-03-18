def p(d):
    r = []
    for i in range(len(d)):
        x = d[i]
        if x > 0:
            if x % 2 == 0:
                r.append(x * 2)
            else:
                r.append(x * 3)
        else:
            if x == 0:
                r.append(0)
            else:
                r.append(x)
    return r
