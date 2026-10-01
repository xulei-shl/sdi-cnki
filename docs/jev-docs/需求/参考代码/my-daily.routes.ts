/**
 * 我的每日路由
 *
 * 提供每日评分文章的查询接口。
 * 需要 user 或 admin 角色。
 */

import { Router } from 'express';
import { requireAuth, requireUser, type AuthRequest } from '../../middleware/auth.js';
import { getDailyArticles, getAvailableDates, getMonthDailyStatus } from '../my-daily.js';
import { getUserLocalDate } from '../timezone.js';
import { scoreForUser, ScoringQueueError } from '../../my-daily-scorer-scheduler.js';

const router = Router();

// 获取当日评分文章列表
router.get('/my-daily', requireAuth, requireUser, async (req: AuthRequest, res) => {
  try {
    const date = req.query.date as string | undefined;
    const result = await getDailyArticles(req.userId!, date);
    res.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : '获取每日文章失败';
    res.status(500).json({ error: message });
  }
});

// 获取可用的评分日期
router.get('/my-daily/dates', requireAuth, requireUser, async (req: AuthRequest, res) => {
  try {
    res.json(await getAvailableDates(req.userId!));
  } catch (error) {
    const message = error instanceof Error ? error.message : '获取日期列表失败';
    res.status(500).json({ error: message });
  }
});

// 获取指定月份每日的状态（用于日历组件圆点展示：green / yellow / red / future）
router.get('/my-daily/calendar-status', requireAuth, requireUser, async (req: AuthRequest, res) => {
  try {
    const month = req.query.month as string | undefined;
    const result = await getMonthDailyStatus(req.userId!, month);
    res.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : '获取日历状态失败';
    res.status(500).json({ error: message });
  }
});

// 立即重新触发当前用户的 JEV 评分（支持 SSE 流式实时推送出分事件）
//
// 同一时刻只允许一个评分任务在执行：已有任务运行时本请求会排队等待，
// 前一个任务结束后自动开始执行。
router.post('/my-daily/refresh', requireAuth, requireUser, async (req: AuthRequest, res) => {
  const isSse = req.headers.accept?.includes('text/event-stream');

  if (!isSse) {
    // 兼容传统非流式调用
    try {
      const date = (req.body?.date as string) || (await getUserLocalDate(req.userId!));
      const username = req.user?.username || 'user';
      const result = await scoreForUser(req.userId!, username, date);

      if (result.skipped && (result as any).reason === 'no_topics') {
        res.status(400).json({ error: '您尚未配置主题领域，请先前往「主题」页面添加关注的主题领域与关键词' });
        return;
      }
      if ((result as any).reason === 'no_articles') {
        res.json({ success: true, message: '该日期暂无新增文章', ...result });
        return;
      }
      if ((result as any).reason === 'duplicate') {
        res.json({ success: true, message: '该日期的评分正在进行中，完成后刷新即可看到结果', ...result });
        return;
      }
      res.json({ success: true, ...result });
    } catch (error) {
      if (error instanceof ScoringQueueError) {
        res.status(429).json({ error: error.message, reason: error.reason });
        return;
      }
      const message = error instanceof Error ? error.message : '重新评分失败';
      res.status(500).json({ error: message });
    }
    return;
  }

  // SSE 流式响应
  res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
  res.setHeader('Cache-Control', 'no-cache, no-transform');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no'); // 禁用 Nginx 等反向代理缓存
  res.flushHeaders?.();

  const sendEvent = (event: string, data: any) => {
    res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  };

  try {
    const date = (req.body?.date as string) || (await getUserLocalDate(req.userId!));
    const username = req.user?.username || 'user';

    const result = await scoreForUser(req.userId!, username, date, (progressEvent) => {
      sendEvent(progressEvent.type, progressEvent);
    });

    if (result.skipped && (result as any).reason === 'no_topics') {
      sendEvent('error', { error: '您尚未配置主题领域，请先前往「主题」页面添加关注的主题领域与关键词' });
      res.end();
      return;
    }

    if ((result as any).reason === 'no_articles') {
      sendEvent('info', { reason: 'no_articles', message: '该日期暂无新增文章', ...result });
      res.end();
      return;
    }

    if ((result as any).reason === 'duplicate') {
      sendEvent('info', {
        reason: 'duplicate',
        message: '该日期的评分正在进行中，请稍候',
        ...result,
      });
      res.end();
      return;
    }

    // 评分结束正常关闭
    res.end();
  } catch (error) {
    if (error instanceof ScoringQueueError) {
      sendEvent('error', { error: error.message, reason: error.reason, statusCode: 429 });
    } else {
      const message = error instanceof Error ? error.message : '重新评分失败';
      sendEvent('error', { error: message });
    }
    res.end();
  }
});

export default router;
