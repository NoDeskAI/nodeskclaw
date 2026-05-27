import type { Context } from 'hono';

export function success<T>(c: Context, data: T, message = 'success') {
  return c.json({ code: 0, message, data });
}

export function paginated<T>(
  c: Context,
  items: T[],
  total: number,
  page: number,
  pageSize: number,
) {
  return c.json({
    code: 0,
    message: 'success',
    data: {
      items,
      total,
      page,
      page_size: pageSize,
      total_pages: Math.ceil(total / pageSize),
    },
  });
}

export function error(c: Context, code: number, errorCode: string, message: string, status = 400) {
  return c.json({ code, error_code: errorCode, message, data: null }, status as 400);
}
