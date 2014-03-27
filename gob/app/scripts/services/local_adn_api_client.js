'use strict';

angular.module('adn').factory('ApiClient', function ($rootScope, $http, ADNConfig) {

  var methods = ['get', 'head', 'post', 'put', 'delete', 'jsonp'];
  var dispatch = function (method) {
    return function (conf) {
      conf.headers = conf.headers || {};
      if ($rootScope.local && $rootScope.local.accessToken) {
        conf.headers.Authorization = 'Bearer ' + $rootScope.local.accessToken;
      }

      conf.url = ADNConfig.get('api_client_root', 'https://alpha-api.app.net/stream/0/') + conf.url;
      conf.method = method;
      if (method === 'post' && conf.data && !conf.headers['Content-Type']) {
        conf.data = jQuery.param(conf.data);
        conf.headers['Content-Type'] = 'application/x-www-form-urlencoded';
      }

      return $http(conf);
    };
  };

  var apiClient = {};

  _.each(methods, function (m) {
    apiClient[m] = dispatch(m);
  });

  apiClient.postJson = function (conf) {
    conf.headers = conf.headers || {};
    conf.headers['Content-Type'] = 'application/json';
    if (!angular.isString(conf.data) && angular.isObject(conf.data) || angular.isArray(conf.data)) {
      conf.data = angular.toJson(conf.data);
    }
    return apiClient.post(conf);
  };


 // look into $resource for this stuff
  apiClient.createChannel = function (channel) {
    return apiClient.post({
      url: '/channels',
      data: channel
    });
  };

  apiClient.updateChannel = function (channel, updates) {
    return apiClient.put({
      url: '/channels/' + channel.id,
      data: updates
    });
  };

  apiClient.getBroadcastChannels = function () {
    return apiClient.get({
      url: '/channels',
      params: {
        include_annotations: 1,
        channel_types: 'net.app.core.broadcast'
      }
    });
  };

  apiClient.getChannel = function (channel_id) {
    return apiClient.get({
      url: '/channels/' + channel_id,
    });
  };

  apiClient.subscribeToChannel = function (channel) {
    return apiClient.post({
      url: '/channels/' + channel.id + '/subscribe',
    });
  };

  apiClient.unsubscribeFromChannel = function (channel) {
    return apiClient.delete({
      url: '/channels/' + channel.id + '/subscribe',
    });
  };

  apiClient.createMessage = function (channel, message) {
    return apiClient.post({
      url: '/channels/' + channel.id + '/messages',
      data: message
    });
  };

  apiClient.getMessages = function (channel) {
    return apiClient.get({
      url: '/channels/' + channel.id + '/messages',
    });
  };

  apiClient.getMultipleUsers = function (ids) {
    return apiClient.get({
      params: {
        ids: ids
      }
    });
  };

  apiClient.searchUsers = function (query) {
    return apiClient.get({
      params: query,
      url: '/users/search'
    });
  };

  // misc stuff
  apiClient.getChannelMetadata = function (channel) {
    var annotation = _.find(channel.annotations, function (annotation) {
      return annotation.type === 'net.app.core.broadcast.metadata' && annotation.value.title && annotation.value.description;
    });
    if (annotation) {
      return annotation.value;
    } else {
      return {
        title: "Channel " + channel.id,
        description: ''
      };
    }
  };

  // ugly hack?
  $rootScope.channels = [];

  apiClient.getBroadcastChannels().success(function (data) {
    $rootScope.channels = _.filter(data.data, function (channel) {
      return channel.you_subscribed;
    });
  });


  return apiClient;

});
