package com.stockapp.interceptor;

import jakarta.servlet.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingRequestWrapper;
import org.springframework.web.util.ContentCachingResponseWrapper;

import java.io.IOException;

@Slf4j
@Component
public class RequestLoggingInterceptor extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain) throws ServletException, IOException {
        ContentCachingRequestWrapper requestWrapper = new ContentCachingRequestWrapper(request);
        ContentCachingResponseWrapper responseWrapper = new ContentCachingResponseWrapper(response);

        long start = System.currentTimeMillis();

        try {
            filterChain.doFilter(requestWrapper, responseWrapper);
        } finally {
            long duration = System.currentTimeMillis() - start;
            String body = new String(requestWrapper.getContentAsByteArray(), request.getCharacterEncoding() != null ? request.getCharacterEncoding() : "UTF-8");
            if (body.length() > 2000) body = body.substring(0, 2000) + "...";

            log.info(">>> {} {} query={} body={}", request.getMethod(), request.getRequestURI(), request.getQueryString(), body);
            log.info("<<< {} {} status={} {}ms", request.getMethod(), request.getRequestURI(), responseWrapper.getStatus(), duration);

            responseWrapper.copyBodyToResponse();
        }
    }
}
