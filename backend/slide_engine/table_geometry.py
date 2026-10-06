"""Keep native table grid dimensions consistent with its graphic frame."""


def resize(shape, width, height):
    table = shape.table
    before = (shape.width, shape.height,
              tuple(c.width for c in table.columns), tuple(r.height for r in table.rows))
    def distribute(items, attribute, total):
        weights = [getattr(item, attribute) for item in items]
        denominator = sum(weights)
        edge = previous = 0
        for item, weight in zip(items, weights):
            edge += weight
            boundary = round(total * edge / denominator)
            setattr(item, attribute, boundary - previous)
            previous = boundary
    distribute(table.columns, 'width', width)
    distribute(table.rows, 'height', height)
    after = (shape.width, shape.height,
             tuple(c.width for c in table.columns), tuple(r.height for r in table.rows))
    return before != after
